// Local CLI and compatibility exports; the shared report has no Node dependencies.
import {readFile,writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import {query,summarize,htmlReport} from './report-data.js';
export {query,summarize,htmlReport} from './report-data.js';
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href) {
  const [mode,arg,out]=process.argv.slice(2);
  if(mode==='--query')console.log(query(Number(arg||7)));
  else if(mode==='--input') {const result=JSON.parse(await readFile(arg,'utf8'));const s=summarize(result.data);console.log(JSON.stringify(s,null,2));if(out)await writeFile(out,htmlReport(s));}
  else throw Error('Usage: node report.mjs --query 7 | --input query-result.json report.html');
}
