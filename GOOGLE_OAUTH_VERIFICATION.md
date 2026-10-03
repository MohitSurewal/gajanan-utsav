# Gajanan Utsav – Google OAuth / Privacy Verification Update

This build adds the public pages and in-product notices needed for the Google
OAuth/YouTube verification workflow.

## Public URLs after deployment

- https://gajananutsavsamiti.online/
- https://gajananutsavsamiti.online/privacy-policy
- https://gajananutsavsamiti.online/terms

## Google Cloud configuration

Branding:
- Homepage: https://gajananutsavsamiti.online/
- Privacy Policy: https://gajananutsavsamiti.online/privacy-policy
- Terms of Service: https://gajananutsavsamiti.online/terms

Make sure the domain is verified/authorized in Google Cloud.

## After deployment

1. Open the homepage in an incognito window.
2. Confirm the Privacy Policy and Terms links are visible.
3. Open the Privacy Policy URL directly and confirm it returns a normal HTML page.
4. In Google Cloud Branding, request re-verification after the live pages are accessible.
5. Only after the OAuth app is ready for production, reconnect YouTube from:
   Admin -> Videos -> Connect / Reconnect YouTube.

## Important

Never commit Firebase service-account JSON or OAuth client secrets to GitHub.
Keep them in Render environment variables.
