// Exercise generated sharing code, including success/cancel/browser fallback.
// This verifies JavaScript behavior, not physical Safari permission policies.
import {execFileSync} from 'node:child_process';
import {runInNewContext} from 'node:vm';
import {File} from 'node:buffer';
import assert from 'node:assert/strict';

const html=execFileSync(process.env.PYTHON || 'python', ['-c',
  'from public_report_ui import _share_controls_html; print(_share_controls_html("/app/static/reports/public_report_test.pdf"))'], {encoding:'utf8'});
const code=html.match(/<script>([\s\S]*)<\/script>/)[1];
async function test(mode) {
 const nodes=Object.fromEntries(['share','download','status'].map(key=>[key,{disabled:true,textContent:''}]));
 const calls=[];
 const nav={canShare:()=>mode!=='unsupported',share:async data=>{
  calls.push(data);if(mode==='cancel')throw Object.assign(new Error('cancel'),{name:'AbortError'});
  if(mode==='denied')throw Object.assign(new Error('denied'),{name:'NotAllowedError'});
 }};
 runInNewContext(code, {document:{getElementById:key=>nodes[key]},File, navigator:{},window:{parent:{navigator:nav}},
  fetch:async()=>{if(mode==='fetchfail')throw new Error('network');return {ok:true,blob:async()=>new Blob(['%PDF-1.7 test'],{type:'application/pdf'})};}});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(calls.length,0,'sharing must require a click');
 assert.equal(nodes.share.disabled,false);
 await nodes.share.onclick();
 if(mode==='ok') {
  assert.equal(calls.length,1);assert.equal(calls[0].files[0].type,'application/pdf');
  assert.equal(calls[0].files[0].name,'rapport.pdf');assert.equal(nodes.status.textContent,'Rapporten er delt.');
 } else if(mode==='cancel')assert.equal(nodes.status.textContent,'Deling avbrutt.');
 else if(mode==='denied')assert.match(nodes.status.textContent,/kunne ikke fullføres/);
 else {assert.equal(calls.length,0);assert.match(nodes.status.textContent,/Last ned PDF/);}
 assert.equal(nodes.download.href,'/app/static/reports/public_report_test.pdf');
}
for(const mode of ['ok','cancel','unsupported','denied','fetchfail'])await test(mode);
console.log('Generated sharing JavaScript: 5 paths passed');
