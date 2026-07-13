const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.static(path.join(__dirname, 'public')));

app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log('\n');
  console.log('  ╔══════════════════════════════════════════╗');
  console.log('  ║   ⛏️  MINECRAFT-THREEJS  ⛏️              ║');
  console.log('  ╠══════════════════════════════════════════╣');
  console.log(`  ║   Server running on port ${PORT}              ║`);
  console.log(`  ║   Open: http://localhost:${PORT}             ║`);
  console.log('  ╚══════════════════════════════════════════╝');
  console.log('\n  Controls:');
  console.log('    WASD - Move    Space - Jump    Shift - Sprint');
  console.log('    Mouse - Look   Left Click - Break   Right Click - Place');
  console.log('    1-9 - Select block   F - Toggle fly mode');
  console.log('    ESC - Release mouse\n');
});
