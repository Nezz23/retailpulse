S=/private/tmp/claude-501/-Users-nezz/f0c698fc-ed47-43ee-b6dd-72f313d6f224/scratchpad
cd $S/twbx && cp ../before_exec.twb RetailPulse_Dashboard.twb && python3 ~/Projects/RetailPulse/tableau/build_dashboards.py RetailPulse_Dashboard.twb && xmllint --noout RetailPulse_Dashboard.twb || exit 1
pkill -x "Tableau Public"; sleep 2; pkill -9 -x "Tableau Public" 2>/dev/null
rm -f ~/Projects/RetailPulse/tableau/RetailPulse_Dashboard.twbx && zip -qr ~/Projects/RetailPulse/tableau/RetailPulse_Dashboard.twbx RetailPulse_Dashboard.twb Data
open -a "Tableau Public" ~/Projects/RetailPulse/tableau/RetailPulse_Dashboard.twbx
for i in $(seq 1 30); do pgrep -x "Tableau Public" >/dev/null && break; sleep 1; done; sleep 25
screencapture -x $S/screen.png
