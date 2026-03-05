// supabase/functions/sign-out/index.ts
Deno.serve(async (req) => {
  const origin = req.headers.get('origin');
  const corsHeaders = {
    'Access-Control-Allow-Origin': origin || '*',
    'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Credentials': 'true',
  };

  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  const isLocal = Deno.env.get('SUPABASE_URL')?.includes('localhost') || 
                  Deno.env.get('SUPABASE_URL')?.includes('127.0.0.1');
  const sameSite = isLocal ? 'None' : 'Lax';
  
  // Set Max-Age to 0 to instruct the browser to delete the cookie
  const expiredCookie = `trackr_session=; HttpOnly; Path=/; Max-Age=0; SameSite=${sameSite}; Secure`;

  return new Response(JSON.stringify({ message: 'Signed out' }), {
    headers: {
      ...corsHeaders,
      'Content-Type': 'application/json',
      'Set-Cookie': expiredCookie,
    },
    status: 200,
  });
});