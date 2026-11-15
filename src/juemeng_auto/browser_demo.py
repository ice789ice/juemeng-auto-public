"""Playwright adapter constrained to a caller-owned local demo page."""
from urllib.parse import urlsplit

def submit_demo(page,url,script):
    parsed=urlsplit(url)
    if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.port!=5050 or parsed.path!='/' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Only the local demo server is supported')
    page.goto(url)
    page.locator('textarea[name=script]').fill(script)
    with page.expect_navigation(wait_until='domcontentloaded'):
        page.get_by_role('button',name='Analyze',exact=True).click()
    return page.locator('body').inner_text()
