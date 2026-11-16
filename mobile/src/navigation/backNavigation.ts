type RouterBackControls = {
  canGoBack: () => boolean;
  back: () => void;
  replace: (href: any) => void;
};

/** Return to the previous route, or a stable in-app screen for direct links. */
export function goBackOrReplace(router: RouterBackControls, fallback: string) {
  if (router.canGoBack()) {
    router.back();
    return;
  }

  router.replace(fallback);
}
