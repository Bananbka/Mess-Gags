import {
    ChangeDetectionStrategy,
    Component,
    computed,
    DestroyRef,
    effect,
    inject,
    input,
    output,
    signal,
    untracked,
} from '@angular/core';
import {
    AlertTriangle,
    Archive,
    Check,
    CheckCheck,
    Clock,
    Lock,
    LucideAngularModule,
    LucideIconData,
    RefreshCw,
    ShieldAlert,
    ShieldCheck,
    ShieldOff,
    Trash2,
} from 'lucide-angular';

import { DirectoryService } from '../../../core/services/directory.service';
import { DecryptedMessage, DecryptStatus } from '../../../core/services/message.service';
import { AvatarComponent } from '../../../shared/ui/avatar/avatar.component';
import { messageTime } from '../../../shared/utils/display';

/**
 * How a status renders.
 *
 * Every `DecryptStatus` gets its own treatment, because collapsing them makes the interface lie
 * about the guarantee — see `docs/ui-states.md`. In particular:
 *
 *   `no_key`      is transient and normal, so it must not look like an error.
 *   `unverified`  decrypted but unauthenticated: the content may be forged, so it must not look
 *                 like ordinary text.
 *   `failed`      could be tampering, so it must not look like a blank message.
 *   `legacy`      is permanently unreadable, so it must not look like loading.
 *   `plaintext`   carries no confidentiality, so it must not show a lock.
 */
interface StatusView {
    /** Body text when the message itself has none. */
    placeholder: string | null;
    detail: string | null;
    tone: 'normal' | 'pending' | 'warn' | 'danger' | 'inert';
    icon: LucideIconData | null;
}

/**
 * How long a `no_key` message stays quiet before it explains itself.
 *
 * `docs/ui-states.md` calls this state transient and normal, and the client now pulls grants on a
 * backoff starting at 400ms, so the overwhelmingly common case resolves within a beat. Announcing a
 * missing key for that beat trains the reader to ignore the notice — and it is the notice that
 * matters on the rare occasion the key really is absent.
 *
 * The message body is still withheld during the grace period. This delays an explanation, never
 * content: nothing unread is ever shown as though it had been decrypted.
 */
const NO_KEY_GRACE_MS = 1500;

/** The quiet first phase of `no_key`: waiting, with no claim that anything is wrong. */
const SETTLING_VIEW: StatusView = {
    placeholder: 'Decrypting…',
    detail: null,
    tone: 'pending',
    icon: null,
};

const STATUS_VIEWS: Record<DecryptStatus, StatusView> = {
    ok: { placeholder: null, detail: null, tone: 'normal', icon: null },
    plaintext: { placeholder: null, detail: null, tone: 'normal', icon: null },
    no_key: {
        placeholder: 'Waiting for this sender’s key',
        detail: 'They have not wrapped their chain for your device yet. This usually resolves on its own.',
        tone: 'pending',
        icon: Lock,
    },
    unverified: {
        placeholder: null,
        detail: 'Signature did not verify — this content may have been forged.',
        tone: 'warn',
        icon: ShieldAlert,
    },
    failed: {
        placeholder: 'Could not be decrypted',
        detail: 'Tampering, a consumed chain index, or a stale grant. The original content is not recoverable here.',
        tone: 'danger',
        icon: AlertTriangle,
    },
    legacy: {
        placeholder: 'Permanently unreadable',
        detail: 'Encrypted with the pre-migration scheme. There is no key that can open it.',
        tone: 'inert',
        icon: Archive,
    },
};

@Component({
    selector: 'app-message-bubble',
    imports: [LucideAngularModule, AvatarComponent],
    templateUrl: './message-bubble.component.html',
    styleUrl: './message-bubble.component.scss',
    changeDetection: ChangeDetectionStrategy.OnPush,
    host: {
        '[class.is-outgoing]': 'isOwn()',
        '[attr.data-delivery]': 'delivery()',
        // An attribute rather than a `[class]` string: a class-map binding competes with the
        // `[class.is-outgoing]` binding for the same property, and the tone styles need both to be
        // reliably present at once.
        '[attr.data-tone]': 'view().tone',
    },
})
export class MessageBubbleComponent {
    private readonly directory = inject(DirectoryService);
    private readonly destroyRef = inject(DestroyRef);

    readonly message = input.required<DecryptedMessage>();
    /** Groups and channels label each sender; a two-party chat does not need to. */
    readonly showSender = input(true);
    readonly canDelete = input(false);
    /**
     * Where an outgoing message is in its journey.
     *
     * Present so a message still being sent renders through this component rather than a parallel
     * one. Two implementations of a bubble cannot be kept pixel-identical by hand, and any drift
     * shows up as the message restyling itself the instant the send is accepted.
     */
    readonly delivery = input<'sent' | 'sending' | 'failed'>('sent');

    readonly deleteRequested = output<string>();

    /** True while a freshly seen `no_key` is still within its grace period. */
    private readonly settling = signal(false);

    readonly isOwn = computed(() => this.directory.isMe(this.message().senderId));
    readonly sender = computed(() => this.directory.lookup(this.message().senderId));
    readonly time = computed(() => messageTime(this.message().createdAt));

    readonly view = computed(() => {
        const status = this.message().status;
        return status === 'no_key' && this.settling() ? SETTLING_VIEW : STATUS_VIEWS[status];
    });

    /** Only ever true when a signature was actually checked and passed — never a default. */
    readonly showVerified = computed(() => this.message().senderVerified && this.message().status === 'ok');

    /** A channel post is signed but not confidential, so it gets the opposite of a lock. */
    readonly showBroadcastMark = computed(() => this.message().status === 'plaintext');

    constructor() {
        let timer: ReturnType<typeof setTimeout> | null = null;

        // Only the first sighting of a no_key gets the grace period. A message still unreadable after
        // the retries have run stays escalated rather than flickering back to a calm state.
        effect(() => {
            const isMissingKey = this.message().status === 'no_key';

            untracked(() => {
                if (timer) {
                    clearTimeout(timer);
                    timer = null;
                }

                this.settling.set(isMissingKey);
                if (isMissingKey) {
                    timer = setTimeout(() => this.settling.set(false), NO_KEY_GRACE_MS);
                }
            });
        });

        this.destroyRef.onDestroy(() => {
            if (timer) {
                clearTimeout(timer);
            }
        });
    }

    /** The status glyph for our own message: pending, delivered, or rejected. */
    readonly deliveryIcon = computed(() => {
        switch (this.delivery()) {
            case 'sending':
                return Clock;
            case 'failed':
                return AlertTriangle;
            default:
                return Check;
        }
    });

    readonly checkIcon = Check;
    readonly checkCheckIcon = CheckCheck;
    readonly refreshIcon = RefreshCw;
    readonly shieldCheckIcon = ShieldCheck;
    readonly shieldOffIcon = ShieldOff;
    readonly trashIcon = Trash2;
}
