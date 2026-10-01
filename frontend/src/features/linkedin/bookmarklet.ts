import { capturePage } from './capture'

/** The bookmark's source: read the page (capturePage), then open the local import window with
 * the data in its URL fragment (never sent anywhere). If LinkedIn keeps the opener link, the
 * import window also asks for the data by postMessage (a second channel for long listings).
 * A blocked pop-up shows a small notice on the page instead of an alert. */
export function bookmarkletSource(origin: string): string {
  return `(function(){var capture=${capturePage.toString()};var o=${JSON.stringify(origin)};var d;try{d=capture(document,location)}catch(e){d={v:1,url:location.href,error:String(e),sources:{}}}var w=window.open(o+'/import#c='+encodeURIComponent(JSON.stringify(d)),'jobhunter-import','popup,width=880,height=960');if(!w){var b=document.createElement('div');b.textContent='Job Hunter: allow pop-ups for linkedin.com, then click the bookmark again.';b.style.cssText='position:fixed;top:12px;right:12px;z-index:2147483647;background:black;color:white;padding:10px 14px;border-radius:8px;font:14px system-ui,sans-serif';document.body.appendChild(b);setTimeout(function(){b.remove()},7000);return}var h=function(e){if(e.origin===o&&e.data==='jobhunter-ready'){try{w.postMessage({type:'jobhunter-capture',data:d},o)}catch(x){}removeEventListener('message',h)}};addEventListener('message',h)})()`
}

export function bookmarkletHref(origin: string): string {
  return 'javascript:' + encodeURIComponent(bookmarkletSource(origin))
}
