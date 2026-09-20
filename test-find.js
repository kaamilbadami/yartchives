const fs = require('fs');

const code = fs.readFileSync('app.js', 'utf8');
const lines = code.split('\n');

for (let i = 0; i < lines.length; i++) {
  if (lines[i].includes('loadSavedState')) {
     console.log(`Line ${i + 1}: ${lines[i]}`);
  }
}
