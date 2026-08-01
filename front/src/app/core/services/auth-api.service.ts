import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';

import { SuccessResponse } from '../models/api.model';
import { UserProfile } from '../models/chat.model';
import { ConfigService } from './config.service';

export interface RegisterRequest {
    full_name: string;
    username: string;
    password: string;
    email: string;
    phone_number: string;
    /** Legacy RSA fields, still required by the backend schema during the transition. */
    public_key: string;
    encrypted_private_key: string;
}

export interface LoginRequest {
    username: string;
    password: string;
}

@Injectable({ providedIn: 'root' })
export class AuthApiService {
    private readonly http = inject(HttpClient);
    private readonly configService = inject(ConfigService);

    private get apiUrl(): string {
        return this.configService.apiUrl + 'auth/';
    }

    register(data: RegisterRequest): Observable<UserProfile> {
        return this.http.post<SuccessResponse<UserProfile>>(`${this.apiUrl}register`, data).pipe(map((r) => r.data));
    }

    /**
     * Re-issue the OTP.
     *
     * Takes no address: the endpoint reads the recipient from the (unverified) session that
     * `register` established, so a caller cannot aim verification mail at somebody else's inbox.
     */
    resendVerificationEmail(): Observable<unknown> {
        return this.http
            .post<SuccessResponse<unknown>>(`${this.apiUrl}get-verification-email`, {})
            .pipe(map((r) => r.data));
    }

    verifyEmail(email: string, otp: string): Observable<UserProfile> {
        return this.http
            .post<SuccessResponse<UserProfile>>(`${this.apiUrl}verify-email`, { email, otp })
            .pipe(map((r) => r.data));
    }

    login(data: LoginRequest): Observable<UserProfile> {
        return this.http.post<SuccessResponse<UserProfile>>(`${this.apiUrl}login`, data).pipe(map((r) => r.data));
    }

    logout(): Observable<unknown> {
        return this.http.post<SuccessResponse<unknown>>(`${this.apiUrl}logout`, {}).pipe(map((r) => r.data));
    }

    refresh(): Observable<unknown> {
        return this.http.post<SuccessResponse<unknown>>(`${this.apiUrl}refresh`, {}).pipe(map((r) => r.data));
    }

    me(): Observable<UserProfile> {
        return this.http
            .get<SuccessResponse<UserProfile>>(`${this.configService.apiUrl}profile/me`)
            .pipe(map((r) => r.data));
    }
}
