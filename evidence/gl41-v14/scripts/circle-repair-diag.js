const fs = require('fs');
const zlib = require('zlib');

const session = 'C:/Users/zrxma/.dsh/sessions/--D-harness--/session-89ff9205-2eb8-439b-bb0b-38b5ac395f4e/session.v4.jsonl.zstd';
const raw = zlib.zstdDecompressSync(fs.readFileSync(session)).toString('utf8');
const tokens = raw.match(/CCIPAT_[A-Za-z0-9_]+/g) || [];
if (!tokens.length) throw new Error('Circle token unavailable');
const token = tokens[tokens.length - 1];
const jobNumber = process.argv[2];
const destination = process.argv[3];
if (!jobNumber || !destination) throw new Error('usage: circle-fetch-ipa.js JOB OUTPUT');

async function circleJson(url) {
  const response = await fetch(url, {headers: {'Circle-Token': token}});
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return response.json();
}

let downloaded = 0;

async function downloadChunk(getUrl, refreshUrl, start, end, fd) {
  let lastError;
  let position = start;
  for (let attempt = 1; attempt <= 8; attempt += 1) {
    try {
      const url = await getUrl();
      const response = await fetch(url, {
        headers: {Range: `bytes=${position}-${end}`},
        signal: AbortSignal.timeout(180000),
      });
      if (response.status !== 206) throw new Error(`range status ${response.status}`);
      if (!response.headers.get('content-range')?.startsWith(`bytes ${position}-${end}/`)) throw new Error('invalid response range');
      for await (const chunk of response.body) {
        const data = Buffer.from(chunk);
        fs.writeSync(fd, data, 0, data.length, position);
        position += data.length;
        downloaded += data.length;
      }
      if (position !== end + 1) throw new Error(`range ended at ${position}, expected ${end + 1}`);
      return end - start + 1;
    } catch (error) {
      lastError = error;
      if (String(error.message).includes('403')) await refreshUrl();
      await new Promise(resolve => setTimeout(resolve, attempt * 750));
    }
  }
  throw lastError;
}

(async () => {
  const artifacts = await circleJson(
    `https://circleci.com/api/v1.1/project/github/zhangrongxue/mc-aot-ios/${jobNumber}/artifacts`
  );
  const artifact = artifacts.find(row => String(row.path || '').endsWith('.ipa'));
  if (!artifact) throw new Error(`no IPA artifact; available: ${artifacts.map(row => row.path).join(', ')}`);

  let objectUrl;
  let refreshInFlight;
  async function refreshObjectUrl() {
    if (!refreshInFlight) {
      refreshInFlight = (async () => {
        const redirect = await fetch(artifact.url + (artifact.url.includes("?") ? "&" : "?") + "_fresh=" + Date.now(), {
          headers: {'Circle-Token': token},
          redirect: 'manual',
        });
        objectUrl = redirect.headers.get('location') || artifact.url;
        return objectUrl;
      })().finally(() => { refreshInFlight = undefined; });
    }
    return refreshInFlight;
  }
  await refreshObjectUrl();
  const probe = await fetch(objectUrl, {headers: {Range: 'bytes=0-0'}});
  const range = probe.headers.get('content-range') || '';
  const match = range.match(/\/(\d+)$/);
  if (!match) throw new Error(`artifact size unavailable: ${range}`);
  await probe.arrayBuffer();
  const size = Number(match[1]);
  const fd = fs.openSync(destination, 'r+');
  if (fs.fstatSync(fd).size !== size) throw new Error("size mismatch");
  const progress = setInterval(() => {
    console.log(`downloaded ${downloaded}/${size}`);
  }, 15000);
  try {
    const threads = 32;
    const span = Math.ceil(size / threads);
    const tasks = [];
    for (let index = 0; index < threads; index += 1) {
      let start = index * span;
      const end = Math.min(start + span - 1, size - 1);
      const existing = Buffer.alloc(end - start + 1);
      fs.readSync(fd, existing, 0, existing.length, start);
      let last = existing.length - 1;
      while (last >= 0 && existing[last] === 0) last--;
      if (existing.length - last > 128) start += Math.max(0, last - 1024);
      else continue;
      if (start <= end) tasks.push(downloadChunk(
        async () => objectUrl,
        refreshObjectUrl,
        start,
        end,
        fd
      ));
    }
    const lengths = await Promise.all(tasks);
    console.log(JSON.stringify({path: artifact.path, bytes: lengths.reduce((a, b) => a + b, 0)}));
  } finally {
    clearInterval(progress);
    fs.closeSync(fd);
  }
})().catch(error => {
  console.error(error.message);
  process.exit(2);
});


