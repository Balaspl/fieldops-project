from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session


from .dispatch import verify_jwt_token
from ..database import get_db
from ..models import NotificationTemplate
from ..schemas import TemplateCreate, TemplateResponse, TemplatePreviewRequest, TemplatePreviewResponse
from ..services.template_version_service import create_initial_version,update_version
from app.services.template_engine import render_preview, infer_template_declarations, MessageTemplateEngineError
from app.services.ai.FieldOpsAI.services.prompt_variable_injector import (
    PromptVariableInjectionError,
)

router = APIRouter(
    prefix="/templates",
    tags=["Templates"]
)

@router.post(
    "",
    response_model=TemplateResponse,
)
async def create_template(
    payload: TemplateCreate,
    authorization: str = Depends(
        verify_jwt_token
    ),
    db: Session = Depends(get_db),
):
    """
    Create a legacy platform template or update the
    existing live template and create a new history version.

    One NotificationTemplate row represents the live template.
    TemplateVersion stores its complete version history.
    """

    # --------------------------------------------------
    # Validate before changing the database
    # --------------------------------------------------

    try:
        inferred_paths = (
            infer_template_declarations(
                body=payload.body_template,
                title=payload.title_template,
            )
        )

        variables = sorted(set(inferred_paths))

    except (PromptVariableInjectionError, MessageTemplateEngineError):
        raise HTTPException(
            status_code=400,
            detail="Template validation failed.",
        ) from None

    # --------------------------------------------------
    # Create or update atomically
    # --------------------------------------------------

    try:
        existing = (
            db.query(NotificationTemplate)
            .filter(
                NotificationTemplate.type
                == payload.type,

                NotificationTemplate.channel
                == payload.channel,

                NotificationTemplate.locale
                == payload.locale,

                NotificationTemplate.tenant_id
                == "**platform**",

                NotificationTemplate.agent_type
                == "CommsAgent",

                NotificationTemplate.is_active
                .is_(True),

                NotificationTemplate.is_deleted
                .is_(False),
            )
            .with_for_update()
            .first()
        )

        # ----------------------------------------------
        # Existing live template:
        # update the same row and create version history
        # ----------------------------------------------

        if existing is not None:
            existing.name = payload.name
            existing.format = payload.format
            existing.title_template = (
                payload.title_template
            )
            existing.body_template = (
                payload.body_template
            )
            existing.variables = variables

            update_version(
                db=db,
                template=existing,
                change_summary=(
                    "Legacy template update"
                ),
                actor_id="system",
                tenant_id="**platform**",
            )

            db.commit()
            db.refresh(existing)

            return existing

        # ----------------------------------------------
        # First template:
        # create live row and version 1 together
        # ----------------------------------------------

        new_template = NotificationTemplate(
            name=payload.name,
            type=payload.type,
            channel=payload.channel,
            locale=payload.locale,
            format=payload.format,
            title_template=(
                payload.title_template
            ),
            body_template=(
                payload.body_template
            ),
            variables=variables,
            version=1,
            is_active=True,
            is_deleted=False,
            tenant_id="**platform**",
            agent_type="CommsAgent",
        )

        db.add(new_template)
        db.flush()

        create_initial_version(
            db=db,
            template=new_template,
            created_by="system",
        )

        db.commit()
        db.refresh(new_template)

        return new_template

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=503,
            detail="Template persistence failed.",
        ) from None

        
@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    db: Session = Depends(get_db),
    authorization: str = Depends(verify_jwt_token)
):
    # Only return active platform CommsAgent templates by default
    return db.query(NotificationTemplate).filter(
        NotificationTemplate.is_active == True,
        NotificationTemplate.is_deleted.is_(False),
        NotificationTemplate.tenant_id == "**platform**",
        NotificationTemplate.agent_type == "CommsAgent"
    ).all()

@router.post("/preview", response_model=TemplatePreviewResponse)
async def preview_template(
    payload: TemplatePreviewRequest,
    authorization: str = Depends(verify_jwt_token)
):
    try:
        format_val = getattr(payload, 'format', 'text')
        result = render_preview(
            title_template=payload.title_template,
            body_template=payload.body_template,
            context=payload.mock_context,
            variables=payload.variables,
            format=format_val
        )
        return {
            "rendered_title": result["title"],
            "rendered_body": result["body"]
        }
    except (MessageTemplateEngineError, PromptVariableInjectionError):
        raise HTTPException(status_code=400, detail="Template render failed.") from None
