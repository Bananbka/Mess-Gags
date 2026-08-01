import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { Eye, EyeOff, LucideAngularModule } from 'lucide-angular';

import { SessionService } from '../../../core/services/session.service';
import { BrandMarkComponent } from '../../../shared/ui/brand-mark/brand-mark.component';

@Component({
    selector: 'app-login',
    imports: [ReactiveFormsModule, RouterLink, LucideAngularModule, BrandMarkComponent],
    templateUrl: './login.component.html',
    styleUrl: './login.component.scss',
    changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginComponent {
    private readonly session = inject(SessionService);
    private readonly router = inject(Router);
    private readonly fb = inject(FormBuilder);

    readonly showPassword = signal(false);
    readonly submitting = signal(false);
    readonly error = signal<string | null>(null);

    readonly form = this.fb.nonNullable.group({
        username: ['', Validators.required],
        password: ['', Validators.required],
    });

    readonly eyeIcon = Eye;
    readonly eyeOffIcon = EyeOff;

    /**
     * Signing in only establishes the session cookie. The private bundle is a separate step, so the
     * next stop is always the unlock screen — the password is deliberately not carried across, since
     * holding it in router state to save one keystroke would put it somewhere it need not be.
     */
    async submit(): Promise<void> {
        if (this.form.invalid || this.submitting()) {
            this.form.markAllAsTouched();
            return;
        }

        this.submitting.set(true);
        this.error.set(null);

        const { username, password } = this.form.getRawValue();

        try {
            await this.session.login(username, password);
            await this.router.navigate(['/unlock']);
        } catch (error) {
            this.error.set(this.messageFor(error));
        } finally {
            this.submitting.set(false);
        }
    }

    private messageFor(error: unknown): string {
        if (error instanceof HttpErrorResponse) {
            if (error.status === 401 || error.status === 400) {
                return 'That username and password do not match.';
            }
            if (error.status === 403) {
                return 'This account is not verified yet. Check your email for the code.';
            }
        }
        return 'Could not sign in. Please try again.';
    }
}
