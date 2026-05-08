#!/bin/bash
# Signal 75 deploy script — bumps app.js version and pushes to GitHub
VERSION=$(date +%Y%m%d%H%M)
python3 -c "
import re
with open('/Users/johnhowlett/Signal75/index.html', 'r') as f:
    content = f.read()
content = re.sub(r'app\.js\?v=\d+', f'app.js?v=$VERSION', content)
with open('/Users/johnhowlett/Signal75/index.html', 'w') as f:
    f.write(content)
print(f'Version bumped to $VERSION')
"
cd ~/Signal75
git add index.html app.js
git commit -m "Deploy — app.js v$VERSION"
git push
echo "Deployed v$VERSION"
