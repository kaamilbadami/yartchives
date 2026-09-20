const fs = require('fs');

const code = fs.readFileSync('scripts/stabilize_job_ids.py', 'utf8');

console.log(code.includes('previous_ids'));
