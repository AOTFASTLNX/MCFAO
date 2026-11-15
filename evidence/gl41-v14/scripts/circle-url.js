const fs = require('fs');
const zlib = require('zlib');

const session = 'C:/Users/zrxma/.dsh/sessions/--D-harness--/session-89ff9205-2eb8-439b-bb0b-38b5ac395f4e/session.v4.jsonl.zstd';
const raw = zlib.zstdDecompressSync(fs.readFileSync(session)).toString('utf8');
const tokens = raw.match(/CCIPAT_[A-Za-z0-9_]+/g) || [];
if (!tokens.length) throw new Error('Circle token unavailable');
const token = tokens[tokens.length - 1];
const jobNumber = process.argv[2];

(async () => {
  const response = await fetch(
    `https://circleci.com/api/v1.1/project/github/zhangrongxue/mc-aot-ios/${jobNumber}/artifacts`,
    {headers: {'Circle-Token': token}});
  if (!response.ok) throw new Error(`${response.status} artifacts`);
  const artifacts = await response.json();
  const artifact = artifacts.find(row => String(row.path || '').endsWith('.ipa'));
  if (!artifact) throw new Error('no ipa artifact');
  const redirect = await fetch(artifact.url, {headers: {'Circle-Token': token}, redirect: 'manual'});
  console.log(redirect.headers.get('location') || artifact.url);
})().catch(error => {console.error(error.message); process.exit(1);});
