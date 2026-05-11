#!/bin/bash
# Signal 75 deploy script — bumps app.js and sw.js version and pushes to GitHub
VERSION=$(date +%Y%m%d%H%M)
python3 -c "
import re

# Bump app.js version in index.html
with open('/Users/johnhowlett/Signal75/index.html', 'r') as f:
    content = f.read()
content = re.sub(r'app\.js\?v=\d+', f'app.js?v=$VERSION', content)
with open('/Users/johnhowlett/Signal75/index.html', 'w') as f:
    f.write(content)

# Bump cache version in sw.js — forces all users to get fresh content
with open('/Users/johnhowlett/Signal75/sw.js', 'r') as f:
    sw = f.read()
sw = re.sub(r'signal75-v\d+', f'signal75-v$VERSION', sw)
with open('/Users/johnhowlett/Signal75/sw.js', 'w') as f:
    f.write(sw)

print(f'Version bumped to $VERSION')
"
cd ~/Signal75
git add index.html app.js sw.js
git commit -m "Deploy — app.js v$VERSION"
git push
echo "Deployed v$VERSION"
