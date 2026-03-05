export const fetchTodayEmails = async (accessToken) => {
  try {
    // 1. Create a query string for "newer than 1 day" or since midnight
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    const unixTimestamp = Math.floor(date.getTime() / 1000);
    const query = `after:${unixTimestamp}`; 

    // 2. Fetch the list of Message IDs matching the query
    const listResponse = await fetch(
      `https://gmail.googleapis.com/gmail/v1/users/me/messages?q=${encodeURIComponent(query)}`,
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
      }
    );

    if (!listResponse.ok) {
      throw new Error('Failed to fetch message list from Gmail API');
    }

    const listData = await listResponse.json();

    // If no emails match, return an empty array
    if (!listData.messages || listData.messages.length === 0) {
      return [];
    }

    // 3. Fetch the full details for each Message ID
    // Note: If there are hundreds of emails, you might want to batch this or paginate
    const emails = await Promise.all(
      listData.messages.map(async (message) => {
        const detailResponse = await fetch(
          `https://gmail.googleapis.com/gmail/v1/users/me/messages/${message.id}?format=metadata&metadataHeaders=Subject&metadataHeaders=From`,
          {
            headers: {
              Authorization: `Bearer ${accessToken}`,
            },
          }
        );
        return detailResponse.json();
      })
    );

    // 4. Clean up the data to return something easy to use in React
    return emails.map(email => {
      const headers = email.payload.headers;
      const subject = headers.find(h => h.name === 'Subject')?.value || 'No Subject';
      const from = headers.find(h => h.name === 'From')?.value || 'Unknown Sender';
      
      return {
        id: email.id,
        snippet: email.snippet,
        subject,
        from,
        date: new Date(parseInt(email.internalDate)).toLocaleString()
      };
    });

  } catch (error) {
    console.error("Gmail Service Error:", error);
    throw error;
  }
};