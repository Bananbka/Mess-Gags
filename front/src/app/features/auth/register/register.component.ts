import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { Eye, EyeOff, LucideAngularModule, ShieldCheck } from 'lucide-angular';

import { SessionService } from '../../../core/services/session.service';
import { BrandMarkComponent } from '../../../shared/ui/brand-mark/brand-mark.component';

@Component({
    selector: 'app-register',
    imports: [ReactiveFormsModule, RouterLink, LucideAngularModule, BrandMarkComponent],
    templateUrl: './register.component.html',
    styleUrl: './register.component.scss',
    changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RegisterComponent {
    private readonly session = inject(SessionService);
    private readonly router = inject(Router);
    private readonly fb = inject(FormBuilder);

    readonly showPassword = signal(false);
    readonly submitting = signal(false);
    readonly error = signal<string | null>(null);

    /**
     * Full name and phone number are not in the design, but `POST /auth/register` requires both —
     * the phone number is validated against libphonenumber server-side, so it cannot be defaulted.
     */
    readonly form = this.fb.nonNullable.group({
        fullName: ['', [Validators.required, Validators.maxLength(30)]],
        username: ['', [Validators.required, Validators.minLength(6), Validators.pattern(/^[a-zA-Z][a-zA-Z0-9_]*$/)]],
        email: ['', [Validators.required, Validators.email]],
        phoneNumber: ['', [Validators.required, Validators.pattern(/^\+[1-9]\d{7,14}$/)]],
        password: ['', [Validators.required, Validators.minLength(12), Validators.maxLength(72)]],
    });

    readonly eyeIcon = Eye;
    readonly eyeOffIcon = EyeOff;
    readonly shieldCheckIcon = ShieldCheck;

    async submit(): Promise<void> {
        if (this.form.invalid || this.submitting()) {
            this.form.markAllAsTouched();
            return;
        }

        this.submitting.set(true);
        this.error.set(null);

        const { email } = this.form.getRawValue();

        try {
            await this.session.register(this.form.getRawValue());
            // The OTP is mailed to this address, so the verify screen needs it to label itself.
            await this.router.navigate(['/verify'], { queryParams: { email } });
        } catch (error) {
            this.error.set(this.messageFor(error));
        } finally {
            this.submitting.set(false);
        }
    }

    private messageFor(error: unknown): string {
        if (error instanceof HttpErrorResponse) {
            const detail = error.error?.message ?? error.error?.detail;
            if (typeof detail === 'string') {
                return detail;
            }
            if (error.status === 422) {
                return 'Some of those details were rejected. Check the email and phone number.';
            }
        }
        return 'Could not create the account. Please try again.';
    }
}
