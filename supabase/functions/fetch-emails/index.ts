// supabase/functions/fetch-emails/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })

  try {
    const { accessToken } = await req.json()
    
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const afterTimestamp = Math.floor(today.getTime() / 1000)

    const listUrl = `https://gmail.googleapis.com/gmail/v1/users/me/messages?q=after:${afterTimestamp}`
    const listRes = await fetch(listUrl, {
      headers: { Authorization: `Bearer ${accessToken}` }
    })
    
    const listData = await listRes.json()
    if (!listData.messages) {
      return new Response(JSON.stringify({ emails: [] }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    const emailPromises = listData.messages.slice(0, 20).map(async (msg: any) => {
      const detailRes = await fetch(
        `https://gmail.googleapis.com/gmail/v1/users/me/messages/${msg.id}?format=metadata&metadataHeaders=Subject&metadataHeaders=From`,
        { headers: { Authorization: `Bearer ${accessToken}` } }
      )
      return await detailRes.json()
    })

    const emails = await Promise.all(emailPromises)

    return new Response(JSON.stringify({ emails }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 200,
    })

  } catch (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 400,
    })
  }
})