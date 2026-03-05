import { useState, useEffect } from 'react';
import { supabase } from './supabaseClient';
import './App.css';

export default function App() {
  const [session, setSession] = useState(() => {
    const saved = localStorage.getItem('trackr_profile');
    return saved ? JSON.parse(saved) : null;
  });
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  const [emails, setEmails] = useState(null);
  const [isFetchingEmails, setIsFetchingEmails] = useState(false);

  useEffect(() => {
    /* global google */
    const initializeGoogle = () => {
      if (!session && window.google) {
        google.accounts.id.initialize({
          client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
          callback: handleGoogleSignIn,
        });

        google.accounts.id.renderButton(
          document.getElementById("googleBtn"),
          { theme: "outline", size: "large", width: "350", shape: "pill" }
        );
      }
    };

    if (window.google) {
      initializeGoogle();
    } else {
      const script = document.querySelector('script[src*="gsi/client"]');
      if (script) script.addEventListener('load', initializeGoogle);
    }
  }, [session]);

  const handleGoogleSignIn = async (response) => {
    setLoading(true);
    setError(null);
    try {
      const { data, error: funcError } = await supabase.functions.invoke('auth-handler', {
        body: { idToken: response.credential, action: 'google-login' }
      });

      if (funcError) throw new Error(funcError.message);
      if (data?.error) throw new Error(data.error);

      const profileData = { ...data.user };
      localStorage.setItem('trackr_profile', JSON.stringify(profileData));
      setSession(profileData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSignOut = async () => {
    try {
      await supabase.functions.invoke('sign-out');
    } catch (err) {
      console.error(err);
    } finally {
      localStorage.removeItem('trackr_profile');
      setSession(null);
      setEmails(null);
    }
  };

  const handleConnectGmail = () => {
    if (!window.google) return;
    setError(null);

    const client = window.google.accounts.oauth2.initTokenClient({
      client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
      scope: 'https://www.googleapis.com/auth/gmail.readonly', 
      callback: async (tokenResponse) => {
        if (tokenResponse && tokenResponse.access_token) {
          setIsFetchingEmails(true);
          try {
            const { data, error } = await supabase.functions.invoke('fetch-emails', {
              body: { accessToken: tokenResponse.access_token }
            });
            
            if (error) throw new Error(error.message);
            if (data?.emails) setEmails(data.emails);
          } catch (err) {
            setError(err.message);
          } finally {
            setIsFetchingEmails(false);
          }
        }
      },
    });

    client.requestAccessToken();
  };

  if (session) {
    return (
      <div className="app-container">
        <div className="glass-panel" style={{ width: '100%', maxWidth: '800px' }}>
          <div className="header">
            <h1 className="logo-text">TRACKR</h1>
          </div>
          
          <div className="profile-section">
            <p className="user-name">{session.email}</p>
          </div>

          {error && <div className="error-box">{error}</div>}

          <div style={{ margin: '2rem 0', textAlign: 'center' }}>
            <button 
              className="btn-primary" 
              onClick={handleConnectGmail} 
              disabled={isFetchingEmails}
            >
              {isFetchingEmails ? 'Fetching...' : 'Fetch Emails'}
            </button>

            {emails && (
              <div style={{ marginTop: '1.5rem', textAlign: 'left', background: '#1e1e1e', color: '#d4d4d4', padding: '1rem', borderRadius: '8px', overflowX: 'auto' }}>
                <pre style={{ margin: 0, fontSize: '0.875rem' }}>
                  {JSON.stringify(emails, null, 2)}
                </pre>
              </div>
            )}
          </div>

          <button className="btn-primary" onClick={handleSignOut}>
            Sign Out
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      <div className="glass-panel">
        <div className="header">
          <h1 className="logo-text">TRACKR</h1>
        </div>
        <div id="googleBtn"></div>
        {loading && <p className="loading-text">Verifying account...</p>}
      </div>
    </div>
  );
}