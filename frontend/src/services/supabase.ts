/**
 * Supabase client configuration and authentication helpers.
 */

import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
const supabaseRedirectTo =
    import.meta.env.VITE_SUPABASE_REDIRECT_TO || `${window.location.origin}/auth/callback`;

if (!supabaseUrl || !supabaseAnonKey) {
    console.warn('Supabase credentials not configured. Please set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.');
}

export const supabase = createClient(
    supabaseUrl || 'https://placeholder.supabase.co',
    supabaseAnonKey || 'placeholder-key'
);

/**
 * Sign in with Google OAuth.
 */
export async function signInWithGoogle() {
    const { data, error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
            redirectTo: supabaseRedirectTo,
        },
    });

    if (error) {
        throw error;
    }

    return data;
}

/**
 * Sign in with GitHub OAuth.
 */
export async function signInWithGitHub() {
    const { data, error } = await supabase.auth.signInWithOAuth({
        provider: 'github',
        options: {
            redirectTo: supabaseRedirectTo,
        },
    });

    if (error) {
        throw error;
    }

    return data;
}

/**
 * Sign out the current user.
 */
export async function signOut() {
    const { error } = await supabase.auth.signOut();
    if (error) {
        throw error;
    }
}

/**
 * Get the current session.
 */
export async function getSession() {
    const { data: { session }, error } = await supabase.auth.getSession();
    if (error) {
        throw error;
    }
    return session;
}

/**
 * Get the current user.
 */
export async function getUser() {
    const { data: { user }, error } = await supabase.auth.getUser();
    if (error) {
        throw error;
    }
    return user;
}

