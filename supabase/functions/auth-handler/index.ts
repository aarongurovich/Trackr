import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

// 1. Define reusable CORS headers
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}

Deno.serve(async (req) => {
  // 2. Handle the "Preflight" OPTIONS request immediately
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const { code, action, userId, months } = await req.json()
    
    // Initialize Supabase Admin Client
    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    )

    // NEW ACTION: Handle the historical scan request
    if (action === 'trigger-scan') {
      console.log(`Triggering history scan for user ${userId}: ${months} months`)
      
      const { error: updateError } = await supabase
        .from('users')
        .update({ scan_history_months: months })
        .eq('id', userId)

      if (updateError) throw updateError

      return new Response(JSON.stringify({ success: true }), { 
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 200 
      })
    }

    // ORIGINAL ACTION: Handle Google Login
    if (action === 'google-login') {
      console.log(`Processing google-login for code: ${code?.substring(0, 5)}...`)

      const GOOGLE_CLIENT_ID = Deno.env.get('VITE_GOOGLE_CLIENT_ID')
      const GOOGLE_CLIENT_SECRET = Deno.env.get('VITE_GOOGLE_CLIENT_SECRET')
      const REDIRECT_URI = Deno.env.get('REDIRECT_URI')

      if (!code) {
        throw new Error('Missing authorization code')
      }

      // 3. Exchange Auth Code for Tokens with Google
      const tokenResponse = await fetch('https://oauth2.googleapis.com/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          code,
          client_id: GOOGLE_CLIENT_ID!,
          client_secret: GOOGLE_CLIENT_SECRET!,
          redirect_uri: REDIRECT_URI!,
          grant_type: 'authorization_code',
        }),
      });

      const tokenData = await tokenResponse.json();

      if (!tokenResponse.ok) {
        console.error("GOOGLE ERROR DETAIL:", JSON.stringify(tokenData));
        throw new Error(tokenData.error_description || tokenData.error || 'Bad Request');
      }

      // 4. Let Supabase Auth handle the Google ID token
      const { data: authData, error: authError } = await supabase.auth.signInWithIdToken({
        provider: 'google',
        token: tokenData.id_token,
      })

      if (authError) {
        console.error("Supabase Auth Error:", authError)
        throw authError
      }

      // 4b. Check if user already exists BEFORE upserting
      const { data: existingUser } = await supabase
        .from('users')
        .select('id')
        .eq('id', authData.user.id)
        .maybeSingle() // Use maybeSingle to avoid errors if 0 rows are returned
        
      const isNewUser = !existingUser;

      // 5. Store/Update the user record
      const updatePayload: any = {
        id: authData.user.id,
        email: authData.user.email,
        full_name: authData.user.user_metadata?.full_name || authData.user.user_metadata?.name || '',
        google_access_token: tokenData.access_token,
        last_login: new Date().toISOString()
      }

      if (tokenData.refresh_token) {
        updatePayload.refresh_token = tokenData.refresh_token;
      }

      const { error: dbError } = await supabase
        .from('users')
        .upsert(updatePayload, { onConflict: 'email' })

      if (dbError) {
        console.error("Database Upsert Error:", dbError)
        throw dbError
      }

      // 6. Return the native Supabase session AND the new user flag to React
      return new Response(JSON.stringify({ 
        user: authData.user,
        session: authData.session,
        is_new_user: isNewUser
      }), { 
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 200 
      })
    }

    throw new Error('Invalid request parameters')

  } catch (err) {
    console.error("Critical Auth Error:", err.message)
    return new Response(JSON.stringify({ error: err.message }), { 
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 401 
    })
  }
})