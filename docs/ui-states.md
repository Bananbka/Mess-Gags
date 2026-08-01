# UI states the client must handle

End-to-end encryption creates states an ordinary messenger UI has no concept of. Collapsing them
into "text" or "error" makes the interface **lie about the security guarantee** — which is worse
than showing nothing, because a user cannot tell a message they are not meant to read from one that
failed to arrive intact.

`MessageService.decrypt()` returns an explicit `DecryptStatus` for exactly this reason. Every value
below needs its own visual treatment.

## Message-level states

| Status | Meaning | Must NOT look like |
|---|---|---|
| `ok` | Decrypted and signature verified | — |
| `no_key` | We hold no grant for this sender's chain **yet** | An error. This is transient and normal — the sender simply has not wrapped their chain for us. It usually resolves on its own. |
| `unverified` | Decrypted, but the signature did not verify | Ordinary text. The content may be forged. |
| `failed` | Decryption failed outright | A blank message. Could be tampering, a consumed chain index, or a stale grant. |
| `plaintext` | Legacy unencrypted message, or a channel post | An encrypted message. The lock affordance must be absent. |
| `legacy` | Pre-migration RSA content | A loading state. It is **permanently** unreadable. |

Messages also carry `senderVerified`. Show the verified indicator only when a signature was
actually checked and passed — never as a default.

## Conversation-level states

- **History floor** — "Messages before you joined are unavailable." Permanent, not loading. The
  server withholds pre-join ciphertext entirely so it cannot leak sender, timing, size or reply
  structure.
- **Encryption boundary** — "Messages before this point were not encrypted." Group history from
  before encryption was enabled stays plaintext forever; it is never retroactively sealed.
- **Re-keying** — brief state after a member joins or leaves while the chat opens a new epoch.
- **Send blocked** — the server rejected a send with `409 EPOCH_STALE` because the chat re-keyed
  mid-compose. The client re-encrypts from plaintext and retries automatically; surface it only if
  the retry also fails.

## Security-critical states

These two carry the most weight and should be the least like ordinary chrome.

**Safety number** — 12 groups of 5 digits, plus a QR code. Two users compare it out of band. This
is the **only** defence against the server substituting a public key, so it must be reachable in
one or two taps, not buried. It needs a distinct **key-changed** variant: when a peer's key
changes, the number changes, and the user must be told loudly rather than silently re-trusting.

**Member verification failure** — the client recomputes `member_set_hash` from the roster before
wrapping keys and refuses if it disagrees with the epoch's commitment. That means the server may
have inserted a device that would receive future messages. This is the highest-severity state in
the app: it should be unmistakable, block key distribution, and read as "the server may be lying to
you." The backend stores the hash but **cannot** enforce this check — only the client can.

**Channel badge** — channels are signed but **not** encrypted, deliberately (see
`docs/crypto-spec-v1.md` §6). If the UI shows the same lock as a private chat, it is claiming a
guarantee that does not exist.

## Flow states

- **Unlock** — after login the private bundle is decrypted with the user's password via Argon2id at
  64 MiB. That takes a noticeable moment on purpose; it is what protects the bundle if the database
  is ever disclosed. It needs a real progress state, not a flash of spinner.
- **Password reset** — destroys the identity irrecoverably. All prior history becomes permanently
  unreadable. The UI must say so plainly *before* the user proceeds, not after.
- Ordinary states still apply: empty chat list, loading, offline/reconnecting, message
  sending/sent/failed.
