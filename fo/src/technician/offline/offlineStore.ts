
import { Platform } from "react-native";
import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import * as SQLite from "expo-sqlite";
import type { SQLiteDatabase } from "expo-sqlite";

export type OfflineRecordType =
  | "dashboard"
  | "jobs"
  | "job-detail"
  | "job-history"
  | "completion-draft"
  | "job-action-queue"
  | "gps-queue";

export interface OfflineScope {
  tenantId: string;
  technicianId: string;
}

const DATABASE_NAME = "fieldops-offline.db";
const DATABASE_KEY_ALIAS = "fieldops:offline:database-key:v1";

const SECURE_STORE_KEY_PREFIX = "fieldops_secure_v1_";

async function getSecureStoreKey(
  logicalKey: string
): Promise<string> {
  const digest = await Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    logicalKey
  );

  return `${SECURE_STORE_KEY_PREFIX}${digest}`;
}

const DEFAULT_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const MAX_RECORD_TTL_MS = 30 * 24 * 60 * 60 * 1000;
const MAX_RECORD_BYTES = 256 * 1024;
const MAX_GPS_QUEUE_RECORD_BYTES = 1024 * 1024;
const MAX_TOTAL_BYTES = 5 * 1024 * 1024;
const MAX_RECORD_COUNT = 200;

const ALLOWED_RECORD_TYPES: readonly OfflineRecordType[] = [
  "dashboard",
  "jobs",
  "job-detail",
  "job-history",
  "completion-draft",
  "job-action-queue",
  "gps-queue",
];

interface StoredOfflineRecord {
  payload_json: string;
  expires_at_ms: number;
}

interface StorageTotals {
  record_count: number;
  total_bytes: number;
}

interface OldestRecord {
  tenant_id: string;
  technician_id: string;
  record_type: string;
  record_id: string;
  payload_bytes: number;
}

let databasePromise: Promise<SQLiteDatabase> | null = null;

let writeDatabasePromise: Promise<SQLiteDatabase> | null = null;

let databaseKeyForConnections: string | null = null;

let offlineDatabaseQueue: Promise<void> = Promise.resolve();

function validateIdentifier(
  value: string,
  fieldName: string,
): string {
  if (
    typeof value !== "string" ||
    value.trim().length === 0 ||
    value.length > 200
  ) {
    throw new Error(`Invalid offline storage ${fieldName}.`);
  }

  return value.trim();
}

function validateScope(scope: OfflineScope): OfflineScope {
  if (!scope || typeof scope !== "object") {
    throw new Error("Offline storage scope is required.");
  }

  return {
    tenantId: validateIdentifier(scope.tenantId, "tenant ID"),
    technicianId: validateIdentifier(
      scope.technicianId,
      "technician ID",
    ),
  };
}

function validateRecordType(
  recordType: OfflineRecordType,
): void {
  if (
    !ALLOWED_RECORD_TYPES.includes(recordType)
  ) {
    throw new Error("Unsupported offline record type.");
  }
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function getUtf8ByteLength(value: string): number {
  return encodeURIComponent(value).replace(
    /%[0-9A-F]{2}/gi,
    "x",
  ).length;
}

async function createDatabase(): Promise<SQLiteDatabase> {
  if (Platform.OS === "web") {
    throw new Error(
      "Encrypted offline storage is available only in the native mobile app.",
    );
  }

  const secureStoreAvailable =
    await SecureStore.isAvailableAsync();

  if (!secureStoreAvailable) {
    throw new Error(
      "Secure storage is unavailable. Offline data was not saved.",
    );
  }

  const secureDatabaseKeyAlias =
    await getSecureStoreKey(DATABASE_KEY_ALIAS);

  let databaseKey =
    await SecureStore.getItemAsync(secureDatabaseKeyAlias);

  if (!databaseKey) {
    const randomBytes = await Crypto.getRandomBytesAsync(32);
    databaseKey = bytesToHex(randomBytes);

    await SecureStore.setItemAsync(
        secureDatabaseKeyAlias,
        databaseKey
    );
  }

  if (!/^[0-9a-f]{64}$/.test(databaseKey)) {
    throw new Error(
      "The offline database encryption key is invalid.",
    );
  }
  databaseKeyForConnections = databaseKey;

  const database =
    await SQLite.openDatabaseAsync(DATABASE_NAME);

  try {
    // Never continue if this native build lacks SQLCipher.
    const cipher = await database.getFirstAsync<{
      cipher_version: string;
    }>("PRAGMA cipher_version");

    if (!cipher?.cipher_version) {
      throw new Error(
        "SQLCipher is unavailable. Rebuild the native app with SQLCipher enabled before using offline storage.",
      );
    }

    // The key contains only validated hexadecimal characters.
    // Apply it immediately after opening the database.
    await database.execAsync(
      `PRAGMA key = "x'${databaseKey}'";`,
    );

    // Force the database to validate its key before accessing records.
    await database.getFirstAsync(
      "SELECT count(*) AS record_count FROM sqlite_master",
    );

    await database.execAsync(`
      PRAGMA secure_delete = ON;

      CREATE TABLE IF NOT EXISTS offline_records (
        tenant_id TEXT NOT NULL,
        technician_id TEXT NOT NULL,
        record_type TEXT NOT NULL,
        record_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        saved_at_ms INTEGER NOT NULL,
        expires_at_ms INTEGER NOT NULL,
        payload_bytes INTEGER NOT NULL,
        PRIMARY KEY (
          tenant_id,
          technician_id,
          record_type,
          record_id
        )
      );

      CREATE INDEX IF NOT EXISTS offline_records_expiry_idx
      ON offline_records (expires_at_ms);

      CREATE INDEX IF NOT EXISTS offline_records_scope_idx
      ON offline_records (
        tenant_id,
        technician_id,
        expires_at_ms
      );
    `);

    return database;
  } catch (error) {
    await database.closeAsync().catch(() => undefined);
    throw error;
  }
}

async function getDatabase(): Promise<SQLiteDatabase> {
  if (!databasePromise) {
    databasePromise = createDatabase().catch((error) => {
      databasePromise = null;
      throw error;
    });
  }

  return databasePromise;
}

async function getWriteDatabase(): Promise<SQLiteDatabase> {
  if (!writeDatabasePromise) {
    writeDatabasePromise = (async () => {
      // Ensure the primary encrypted database and schema
      // have initialized before opening the writer.
      await getDatabase();

      const databaseKey = databaseKeyForConnections;

      if (!databaseKey) {
        throw new Error(
          "The offline database encryption key is unavailable.",
        );
      }

      const writer = await SQLite.openDatabaseAsync(
        DATABASE_NAME,
        { useNewConnection: true },
      );

      try {
        const cipher = await writer.getFirstAsync<{
          cipher_version: string;
        }>("PRAGMA cipher_version");

        if (!cipher?.cipher_version) {
          throw new Error(
            "SQLCipher is unavailable on the writer connection.",
          );
        }

        // Apply the key before accessing the database schema.
        await writer.execAsync(
          `PRAGMA key = "x'${databaseKey}'";`,
        );

        // Verify that this connection can read the encrypted DB.
        await writer.getFirstAsync(
          "SELECT count(*) AS record_count FROM sqlite_master",
        );

        await writer.execAsync("PRAGMA secure_delete = ON;");

        return writer;
      } catch (error) {
        await writer.closeAsync().catch(() => undefined);
        throw error;
      }
    })().catch((error) => {
      writeDatabasePromise = null;
      throw error;
    });
  }

  return writeDatabasePromise;
}

async function withSerializedDatabaseOperation<T>(
  operation: (database: SQLiteDatabase) => Promise<T>,
): Promise<T> {
  const previousOperation = offlineDatabaseQueue;

  let releaseOperation!: () => void;

  offlineDatabaseQueue = new Promise<void>((resolve) => {
    releaseOperation = resolve;
  });

  await previousOperation;

  try {
    const database = await getWriteDatabase();
    return await operation(database);
  } finally {
    releaseOperation();
  }
}

async function withSerializedWrite<T>(
  operation: (transaction: SQLiteDatabase) => Promise<T>,
): Promise<T> {
  return withSerializedDatabaseOperation(async (transaction) => {
    await transaction.execAsync("BEGIN IMMEDIATE");

    try {
      const result = await operation(transaction);

      await transaction.execAsync("COMMIT");

      return result;
    } catch (error) {
      await transaction.execAsync("ROLLBACK").catch(
        () => undefined,
      );

      throw error;
    }
  });
}

async function purgeExpiredWithDatabase(
  database: SQLiteDatabase,
): Promise<void> {
  await database.runAsync(
    "DELETE FROM offline_records WHERE expires_at_ms <= ?",
    Date.now(),
  );
}

export async function purgeExpiredOfflineRecords(): Promise<void> {
  await withSerializedDatabaseOperation(async (database) => {
    await purgeExpiredWithDatabase(database);
  });
}

export async function setOfflineRecord<T extends object>(
  scope: OfflineScope,
  recordType: OfflineRecordType,
  recordId: string,
  data: T,
  ttlMs: number = DEFAULT_TTL_MS,
): Promise<void> {
  const safeScope = validateScope(scope);
  validateRecordType(recordType);

  const safeRecordId = validateIdentifier(
    recordId,
    "record ID",
  );

  if (
    data === null ||
    typeof data !== "object" ||
    !Number.isFinite(ttlMs) ||
    ttlMs <= 0
  ) {
    throw new Error("Invalid offline record data or retention.");
  }

  const payloadJson = JSON.stringify(data);

  if (typeof payloadJson !== "string") {
    throw new Error("Offline record could not be serialized.");
  }

  const payloadBytes = getUtf8ByteLength(payloadJson);

  if (
    payloadBytes >
    (recordType === "gps-queue"
      ? MAX_GPS_QUEUE_RECORD_BYTES
      : MAX_RECORD_BYTES)
  ) {
    throw new Error(
      "Offline record exceeds the allowed storage size.",
    );
  }

  const now = Date.now();
  const expiresAt = now + Math.min(ttlMs, MAX_RECORD_TTL_MS);

  await withSerializedWrite(async (transaction) => {
    await transaction.runAsync(
      "DELETE FROM offline_records WHERE expires_at_ms <= ?",
      Date.now(),
    );

    const existing = await transaction.getFirstAsync<{
      payload_bytes: number;
    }>(
      `SELECT payload_bytes
      FROM offline_records
      WHERE tenant_id = ?
        AND technician_id = ?
        AND record_type = ?
        AND record_id = ?
      LIMIT 1`,
      safeScope.tenantId,
      safeScope.technicianId,
      recordType,
      safeRecordId
    );

    const totals = await transaction.getFirstAsync<StorageTotals>(
      `SELECT
        COUNT(*) AS record_count,
        COALESCE(SUM(payload_bytes), 0) AS total_bytes
      FROM offline_records`
    );

    let recordCount =
      Number(totals?.record_count ?? 0) +
      (existing ? 0 : 1);

    let totalBytes =
      Number(totals?.total_bytes ?? 0) -
      Number(existing?.payload_bytes ?? 0) +
      payloadBytes;

    while (
      recordCount > MAX_RECORD_COUNT ||
      totalBytes > MAX_TOTAL_BYTES
    ) {
      const oldest = await transaction.getFirstAsync<OldestRecord>(
        `SELECT
          tenant_id,
          technician_id,
          record_type,
          record_id,
          payload_bytes
        FROM offline_records
        WHERE record_type NOT IN (
          'job-action-queue',
          'completion-draft',
          'gps-queue'
        )
          AND NOT (
            tenant_id = ?
            AND technician_id = ?
            AND record_type = ?
            AND record_id = ?
          )
        ORDER BY saved_at_ms ASC
        LIMIT 1`,
        safeScope.tenantId,
        safeScope.technicianId,
        recordType,
        safeRecordId
      );

      if (!oldest) {
        throw new Error(
          "Offline storage is full. Existing pending actions, drafts, and GPS data were preserved."
        );
      }

      await transaction.runAsync(
        `DELETE FROM offline_records
        WHERE tenant_id = ?
          AND technician_id = ?
          AND record_type = ?
          AND record_id = ?`,
        oldest.tenant_id,
        oldest.technician_id,
        oldest.record_type,
        oldest.record_id
      );

      recordCount -= 1;
      totalBytes -= oldest.payload_bytes;
    }

    await transaction.runAsync(
      `INSERT OR REPLACE INTO offline_records (
        tenant_id,
        technician_id,
        record_type,
        record_id,
        payload_json,
        saved_at_ms,
        expires_at_ms,
        payload_bytes
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      safeScope.tenantId,
      safeScope.technicianId,
      recordType,
      safeRecordId,
      payloadJson,
      now,
      expiresAt,
      payloadBytes,
    );
  });
}

export async function getOfflineRecord<T>(
  scope: OfflineScope,
  recordType: OfflineRecordType,
  recordId: string,
): Promise<T | null> {
  const safeScope = validateScope(scope);
  validateRecordType(recordType);

  const safeRecordId = validateIdentifier(
    recordId,
    "record ID",
  );

  return withSerializedDatabaseOperation(async (database) => {
    const record = await database.getFirstAsync<StoredOfflineRecord>(
      `SELECT payload_json, expires_at_ms
      FROM offline_records
      WHERE tenant_id = ?
        AND technician_id = ?
        AND record_type = ?
        AND record_id = ?
      LIMIT 1`,
      safeScope.tenantId,
      safeScope.technicianId,
      recordType,
      safeRecordId,
    );

    if (!record) {
      return null;
    }

    if (record.expires_at_ms <= Date.now()) {
      await database.runAsync(
        `DELETE FROM offline_records
        WHERE tenant_id = ?
          AND technician_id = ?
          AND record_type = ?
          AND record_id = ?`,
        safeScope.tenantId,
        safeScope.technicianId,
        recordType,
        safeRecordId,
      );

      return null;
    }

    try {
      return JSON.parse(record.payload_json) as T;
    } catch {
      await database.runAsync(
        `DELETE FROM offline_records
        WHERE tenant_id = ?
          AND technician_id = ?
          AND record_type = ?
          AND record_id = ?`,
        safeScope.tenantId,
        safeScope.technicianId,
        recordType,
        safeRecordId,
      );

      return null;
    }
  });
}

export async function deleteOfflineRecord(
  scope: OfflineScope,
  recordType: OfflineRecordType,
  recordId: string,
): Promise<void> {
  const safeScope = validateScope(scope);
  validateRecordType(recordType);

  const safeRecordId = validateIdentifier(
    recordId,
    "record ID",
  );

  await withSerializedDatabaseOperation(async (database) => {
    await database.runAsync(
      `DELETE FROM offline_records
      WHERE tenant_id = ?
        AND technician_id = ?
        AND record_type = ?
        AND record_id = ?`,
      safeScope.tenantId,
      safeScope.technicianId,
      recordType,
      safeRecordId,
    );
  });
}


export async function clearOfflineScope(
  scope: OfflineScope,
): Promise<void> {
  const safeScope = validateScope(scope);

  await withSerializedDatabaseOperation(async (database) => {
    await database.runAsync(
      `DELETE FROM offline_records
      WHERE tenant_id = ?
        AND technician_id = ?`,
      safeScope.tenantId,
      safeScope.technicianId,
    );
  });
}