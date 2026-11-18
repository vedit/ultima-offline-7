// Private, read-only presentation of the same report used by the local CLI.
// Access authentication is supplied by Cloudflare, never by a browser header.
import {query, summarize, htmlReport} from './report-data.js';

const HEADERS = {
  'Cache-Control': 'private, no-store',
  'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'X-Robots-Tag': 'noindex, nofollow, noarchive',
};
const TRAFFIC = 'https://dash.cloudflare.com/9ba409024b123e5c7470039a1785b53b/dashboards/c506ce00-b211-4dec-8981-2cb21ebc6c32?filters='+encodeURIComponent(JSON.stringify([[{key:'clientRequestHTTPHost',operator:'in',value:['ultimaoffline7.com','www.ultimaoffline7.com']}]]));
const WEB = 'https://dash.cloudflare.com/9ba409024b123e5c7470039a1785b53b/web-analytics/overview/visits?siteTag~in=0183f0fc3d944f16a66cf2783129d26b&amp;excludeBots=Yes';
const response = (body, status=200, type='text/plain; charset=utf-8') => new Response(body, {status, headers:{...HEADERS, 'Content-Type':type}});

export function liveReport(summary, days, generatedAt) {
  const controls = `<nav aria-label="Analytics views"><a href="${TRAFFIC}">Traffic dashboard ↗</a><a href="${WEB}">Website visitors ↗</a><a href="/cdn-cgi/access/logout">Sign out</a></nav><form method="get"><label for="days">Sessions started in the last</label> <select name="days" id="days">${[1,7,30].map(n=>`<option value="${n}"${n===days?' selected':''}>${n} day${n===1?'':'s'}</option>`).join('')}</select> <button type="submit">Refresh</button> <a href="/summary.json?days=${days}" download="uo7-analytics.json">Download aggregate JSON</a></form><p>Updated ${generatedAt}. Dates use UTC. Reports include opted-in sessions only.</p>`;
  return htmlReport(summary)
    .replace('</style>', 'nav,form{display:flex;flex-wrap:wrap;align-items:center;gap:14px;margin:22px 0}a{color:#e4c885}button,select{font:inherit;background:#2d3d31;color:#fff;border:1px solid #839779;border-radius:5px;padding:8px 12px}button{cursor:pointer}nav a:last-child{margin-left:auto}body{max-width:1150px}.card b{overflow-wrap:anywhere}@media(max-width:500px){body{margin:8px auto;padding:16px}h1{font-size:29px}}@media print{nav,form{display:none}}</style>')
    .replace('</h1>', '</h1>'+controls);
}

export function createDashboard(fetcher=fetch) {
  return {async fetch(request, env, ctx) {
    const url=new URL(request.url);
    // No Static Assets or Service Binding router: ctx.access belongs to this
    // direct Worker invocation. Missing/mismatched configuration fails closed.
    const aud=ctx?.access?.aud;
    if(!env.ACCESS_AUD || !env.ACCESS_EMAIL || !ctx?.access ||
      !(Array.isArray(aud)?aud.includes(env.ACCESS_AUD):aud===env.ACCESS_AUD)) return response('Sign in through Cloudflare Access.',403);
    try {
      const identity=await ctx.access.getIdentity();
      if(identity?.email?.toLowerCase()!==env.ACCESS_EMAIL.toLowerCase()) return response('Access denied.',403);
    } catch {return response('Access denied.',403);}
    if(request.method!=='GET')return response('Method not allowed.',405);
    if(!['/','/summary.json'].includes(url.pathname))return response('Not found.',404);
    const days=Number(url.searchParams.get('days')||7);
    if(![1,7,30].includes(days)||[...url.searchParams.keys()].some(k=>k!=='days'))return response('Choose a 1, 7 or 30 day reporting window.',400);
    if(!env.ANALYTICS_READ_TOKEN || !/^[a-f0-9]{32}$/.test(env.ACCOUNT_ID||''))return response('Reporting is not configured.',503);
    if(env.REPORT_LIMIT && !(await env.REPORT_LIMIT.limit({key:'dashboard'})).success)return response('Please wait a minute before refreshing again.',429);
    try {
      const result=await fetcher(`https://api.cloudflare.com/client/v4/accounts/${env.ACCOUNT_ID}/analytics_engine/sql`,{
        method:'POST',redirect:'error',headers:{'Authorization':`Bearer ${env.ANALYTICS_READ_TOKEN}`,'Content-Type':'text/plain'},
        body:query(days),signal:AbortSignal.timeout(15000),
      });
      if(!result.ok)throw Error('Query unavailable');
      const payload=await result.json();
      const summary=summarize(payload.data), generatedAt=new Date().toISOString();
      if(url.pathname==='/summary.json')return response(JSON.stringify({generatedAt,days,summary},null,2),200,'application/json; charset=utf-8');
      return response(liveReport(summary,days,generatedAt),200,'text/html; charset=utf-8');
    } catch {
      // Do not turn a failed/truncated query into zeroes or reveal raw responses.
      return response('Report unavailable. Refresh to retry, or use a shorter period. No zero values have been substituted.',503);
    }
  }};
}
export default createDashboard();
