"""Renders the Cookidoo login page shown mid-OAuth flow (see `oauth_web.py`).

The page itself is German (end-user facing, same audience as the sibling
bring-mcp-server project); the surrounding Python stays English per
AGENTS.md.
"""

from __future__ import annotations

from html import escape


def render_login_page(*, params: dict[str, str], error_message: str | None) -> str:
    hidden = "\n      ".join(
        f'<input type="hidden" name="{escape(key)}" value="{escape(value)}">'
        for key, value in params.items()
        if value
    )
    error_html = f'<div class="error">{escape(error_message)}</div>' if error_message else ""
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mit Cookidoo anmelden</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f4f2ef;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    padding: 24px;
  }}
  .card {{
    width: 100%;
    max-width: 380px;
    background: #fff;
    border-radius: 16px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.08);
    padding: 32px 28px;
  }}
  h1 {{ font-size: 20px; margin: 0 0 4px; color: #1a1a1a; }}
  p.sub {{ margin: 0 0 24px; color: #666; font-size: 14px; }}
  label {{ display: block; font-size: 13px; font-weight: 600; color: #333; margin-bottom: 6px; }}
  input[type="email"], input[type="password"] {{
    width: 100%;
    padding: 12px 14px;
    border: 1px solid #ddd;
    border-radius: 10px;
    font-size: 16px;
    margin-bottom: 18px;
  }}
  input[type="email"]:focus, input[type="password"]:focus {{
    outline: none;
    border-color: #7ab547;
  }}
  button {{
    width: 100%;
    padding: 13px;
    border: none;
    border-radius: 10px;
    background: #7ab547;
    color: #fff;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
  }}
  button:active {{ opacity: 0.85; }}
  .error {{
    background: #fdecea;
    color: #b3261e;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 14px;
    margin-bottom: 18px;
  }}
  .hint {{ margin-top: 20px; font-size: 12px; color: #999; text-align: center; }}
</style>
</head>
<body>
  <div class="card">
    <h1>Mit Cookidoo anmelden</h1>
    <p class="sub">Verbinde deinen Cookidoo-Account mit diesem MCP-Server.</p>
    {error_html}
    <form method="POST" action="/login/callback" autocomplete="on">
      {hidden}
      <label for="email">E-Mail</label>
      <input type="email" id="email" name="email" required autocomplete="username" inputmode="email">
      <label for="password">Passwort</label>
      <input type="password" id="password" name="password" required autocomplete="current-password">
      <button type="submit">Anmelden</button>
    </form>
    <p class="hint">Deine Zugangsdaten werden nur an die Cookidoo-API übermittelt und verschlüsselt gespeichert.</p>
  </div>
</body>
</html>"""
