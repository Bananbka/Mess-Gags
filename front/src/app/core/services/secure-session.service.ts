import { Injectable } from '@angular/core';

import { b64uDecode, b64uEncode } from '../crypto/primitives';

const DB_NAME = 'ns-secure-session';
const DB_VERSION = 1;
const STORE = 'session';
const KEY_RECORD = 'wrapping-key';
const BLOB_RECORD = 'identity';

/**
 * How long an unlocked identity survives before the password is required again.
 *
 * Long enough that reloading, following a link or restarting the browser does not re-prompt; short
 * enough that an unattended machine does not stay unlocked indefinitely.
 */
const SESSION_TTL_MS = 12 * 60 * 60 * 1000;

export interface PersistedIdentity {
    userId: string;
    deviceId: string;
    signingPrivate: Uint8Array;
    signingPublic: Uint8Array;
    identityPrivate: Uint8Array;
}

interface StoredBlob {
    userId: string;
    iv: number[];
    ciphertext: number[];
    expiresAt: number;
}

/**
 * Keeps an unlocked identity across page reloads.
 *
 * The original design held key material in memory only, on the grounds that anything persisted in a
 * browser is reachable by XSS. That is true of `localStorage`, where the bytes can simply be read and
 * exfiltrated. It is not true here.
 *
 * The private bundle is encrypted under a **non-extractable** `CryptoKey` that lives in IndexedDB.
 * Non-extractable means the browser will not hand the raw bytes to JavaScript at all — there is no
 * API that returns them — so a dump of IndexedDB, a stolen profile directory or a backup contains
 * nothing usable. What an attacker would need is code execution *inside this origin while the entry
 * exists*, at which point they could ask the browser to decrypt on their behalf.
 *
 * So the trade is real but bounded: exfiltrating the identity now requires live code execution rather
 * than read access to storage, and the window is capped by {@link SESSION_TTL_MS} and cleared on
 * sign-out. Chain state is deliberately *not* persisted; it is cheap to rebuild from grants, and a
 * sender simply mints a new chain.
 */
@Injectable({ providedIn: 'root' })
export class SecureSessionService {
    private open(): Promise<IDBDatabase> {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);
            request.onupgradeneeded = () => {
                if (!request.result.objectStoreNames.contains(STORE)) {
                    request.result.createObjectStore(STORE);
                }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    private run<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
        return this.open().then(
            (db) =>
                new Promise<T>((resolve, reject) => {
                    const request = action(db.transaction(STORE, mode).objectStore(STORE));
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => reject(request.error);
                })
        );
    }

    /** Encrypt and store the identity so the next page load does not need the password. */
    async persist(identity: PersistedIdentity): Promise<void> {
        try {
            // `extractable: false` is the whole point — the raw key can never be read back out.
            const key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, [
                'encrypt',
                'decrypt',
            ]);

            const iv = crypto.getRandomValues(new Uint8Array(12));
            const plaintext = new TextEncoder().encode(
                JSON.stringify({
                    userId: identity.userId,
                    deviceId: identity.deviceId,
                    signingPrivate: b64uEncode(identity.signingPrivate),
                    signingPublic: b64uEncode(identity.signingPublic),
                    identityPrivate: b64uEncode(identity.identityPrivate),
                })
            );

            const ciphertext = new Uint8Array(
                await crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv as BufferSource }, key, plaintext as BufferSource)
            );

            const blob: StoredBlob = {
                userId: identity.userId,
                iv: Array.from(iv),
                ciphertext: Array.from(ciphertext),
                expiresAt: Date.now() + SESSION_TTL_MS,
            };

            await this.run('readwrite', (store) => store.put(key, KEY_RECORD));
            await this.run('readwrite', (store) => store.put(blob, BLOB_RECORD));
        } catch {
            // Private browsing, blocked storage, or a quota failure. Not fatal: the user is unlocked
            // for this page load and will simply be asked again next time.
        }
    }

    /** The stored identity, or null when there is none, it expired, or it belongs to someone else. */
    async restore(expectedUserId: string): Promise<PersistedIdentity | null> {
        try {
            const key = await this.run<CryptoKey | undefined>('readonly', (store) => store.get(KEY_RECORD));
            const blob = await this.run<StoredBlob | undefined>('readonly', (store) => store.get(BLOB_RECORD));

            if (!key || !blob) {
                return null;
            }

            // A different account signed in on this browser, or the window has passed.
            if (blob.userId !== expectedUserId || blob.expiresAt < Date.now()) {
                await this.clear();
                return null;
            }

            const plaintext = await crypto.subtle.decrypt(
                { name: 'AES-GCM', iv: new Uint8Array(blob.iv) as BufferSource },
                key,
                new Uint8Array(blob.ciphertext) as BufferSource
            );

            const parsed = JSON.parse(new TextDecoder().decode(plaintext)) as Record<string, string>;

            return {
                userId: parsed['userId'],
                deviceId: parsed['deviceId'],
                signingPrivate: b64uDecode(parsed['signingPrivate']),
                signingPublic: b64uDecode(parsed['signingPublic']),
                identityPrivate: b64uDecode(parsed['identityPrivate']),
            };
        } catch {
            // Tampered, unreadable, or storage unavailable. Fail closed: ask for the password.
            await this.clear();
            return null;
        }
    }

    async clear(): Promise<void> {
        try {
            await this.run('readwrite', (store) => store.delete(KEY_RECORD));
            await this.run('readwrite', (store) => store.delete(BLOB_RECORD));
        } catch {
            // Nothing to clear, or storage is gone. Either way there is nothing left to do.
        }
    }
}
