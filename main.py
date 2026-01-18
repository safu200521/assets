#!/usr/bin/env python3
"""
Bug Bounty Program Monitor
Monitors bounty-targets-data repository for program changes
Sends notifications via Discord/Telegram when assets are added/removed
"""

import requests
import json
import time
import os
from datetime import datetime
from typing import Dict, List, Set

class BountyMonitor:
    def __init__(self, discord_webhook=None, telegram_bot_token=None, telegram_chat_id=None):
        self.discord_webhook = discord_webhook
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.data_url = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/"
        self.platforms = ["hackerone", "bugcrowd", "intigriti", "yeswehack", "hackenproof"]
        self.state_file = "bounty_monitor_state.json"
        self.previous_state = self.load_state()

    def load_state(self) -> Dict:
        """Load previous state from file"""
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {}

    def save_state(self, state: Dict):
        """Save current state to file"""
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)

    def fetch_program_data(self, platform: str) -> List[Dict]:
        """Fetch program data from bounty-targets-data"""
        try:
            url = f"{self.data_url}{platform}_data.json"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching {platform} data: {e}")
            return []

    def extract_targets(self, program: Dict) -> Set[str]:
        """Extract targets/domains from program"""
        targets = set()
        
        # Handle different target structures
        if 'targets' in program:
            if isinstance(program['targets'], dict):
                for category, items in program['targets'].items():
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                target = item.get('target') or item.get('endpoint') or item.get('asset_identifier')
                                if target:
                                    targets.add(str(target))
                            elif isinstance(item, str):
                                targets.add(item)
            elif isinstance(program['targets'], list):
                for item in program['targets']:
                    if isinstance(item, dict):
                        target = item.get('target') or item.get('endpoint') or item.get('asset_identifier')
                        if target:
                            targets.add(str(target))
                    elif isinstance(item, str):
                        targets.add(item)
        
        return targets

    def compare_programs(self, platform: str, current_data: List[Dict]) -> List[Dict]:
        """Compare current data with previous state and detect changes"""
        changes = []
        current_state = {}
        
        for program in current_data:
            program_name = program.get('name') or program.get('handle') or program.get('program_name')
            if not program_name:
                continue
            
            current_targets = self.extract_targets(program)
            current_state[program_name] = list(current_targets)
            
            # Check if program existed before
            if platform in self.previous_state:
                if program_name in self.previous_state[platform]:
                    previous_targets = set(self.previous_state[platform][program_name])
                    
                    # Find added and removed targets
                    added = current_targets - previous_targets
                    removed = previous_targets - current_targets
                    
                    if added or removed:
                        changes.append({
                            'platform': platform,
                            'program': program_name,
                            'added': list(added),
                            'removed': list(removed),
                            'url': program.get('url') or f"https://{platform}.com"
                        })
                else:
                    # New program
                    if current_targets:
                        changes.append({
                            'platform': platform,
                            'program': program_name,
                            'added': list(current_targets),
                            'removed': [],
                            'url': program.get('url') or f"https://{platform}.com",
                            'new_program': True
                        })
        
        # Update state for this platform
        if platform not in self.previous_state:
            self.previous_state[platform] = {}
        self.previous_state[platform] = current_state
        
        return changes

    def send_discord_notification(self, changes: List[Dict]):
        """Send notification to Discord"""
        if not self.discord_webhook:
            return
        
        for change in changes:
            embeds = []
            
            if change.get('new_program'):
                embed = {
                    "title": f"🆕 New Program: {change['program']}",
                    "description": f"Platform: **{change['platform'].upper()}**",
                    "color": 3066993,  # Green
                    "url": change.get('url', ''),
                    "fields": [],
                    "timestamp": datetime.utcnow().isoformat(),
                    "footer": {"text": "Bug Bounty Monitor"}
                }
                
                if change['added']:
                    targets_text = '\n'.join([f"• `{t}`" for t in change['added'][:10]])
                    if len(change['added']) > 10:
                        targets_text += f"\n... and {len(change['added']) - 10} more"
                    embed['fields'].append({
                        "name": f"📥 Targets ({len(change['added'])})",
                        "value": targets_text,
                        "inline": False
                    })
            else:
                embed = {
                    "title": f"🔄 Program Updated: {change['program']}",
                    "description": f"Platform: **{change['platform'].upper()}**",
                    "color": 15844367,  # Yellow/Orange
                    "url": change.get('url', ''),
                    "fields": [],
                    "timestamp": datetime.utcnow().isoformat(),
                    "footer": {"text": "Bug Bounty Monitor"}
                }
                
                if change['added']:
                    targets_text = '\n'.join([f"• `{t}`" for t in change['added'][:10]])
                    if len(change['added']) > 10:
                        targets_text += f"\n... and {len(change['added']) - 10} more"
                    embed['fields'].append({
                        "name": f"➕ Added ({len(change['added'])})",
                        "value": targets_text,
                        "inline": False
                    })
                
                if change['removed']:
                    targets_text = '\n'.join([f"• `{t}`" for t in change['removed'][:10]])
                    if len(change['removed']) > 10:
                        targets_text += f"\n... and {len(change['removed']) - 10} more"
                    embed['fields'].append({
                        "name": f"➖ Removed ({len(change['removed'])})",
                        "value": targets_text,
                        "inline": False
                    })
            
            embeds.append(embed)
            
            try:
                payload = {"embeds": embeds}
                response = requests.post(self.discord_webhook, json=payload, timeout=10)
                response.raise_for_status()
                print(f"✓ Discord notification sent for {change['program']}")
                time.sleep(1)  # Rate limit
            except Exception as e:
                print(f"✗ Error sending Discord notification: {e}")

    def send_telegram_notification(self, changes: List[Dict]):
        """Send notification to Telegram"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return
        
        for change in changes:
            if change.get('new_program'):
                message = f"🆕 <b>New Program: {change['program']}</b>\n"
                message += f"Platform: <b>{change['platform'].upper()}</b>\n\n"
                
                if change['added']:
                    message += f"📥 <b>Targets ({len(change['added'])}):</b>\n"
                    for target in change['added'][:15]:
                        message += f"• <code>{target}</code>\n"
                    if len(change['added']) > 15:
                        message += f"... and {len(change['added']) - 15} more\n"
            else:
                message = f"🔄 <b>Program Updated: {change['program']}</b>\n"
                message += f"Platform: <b>{change['platform'].upper()}</b>\n\n"
                
                if change['added']:
                    message += f"➕ <b>Added ({len(change['added'])}):</b>\n"
                    for target in change['added'][:10]:
                        message += f"• <code>{target}</code>\n"
                    if len(change['added']) > 10:
                        message += f"... and {len(change['added']) - 10} more\n"
                    message += "\n"
                
                if change['removed']:
                    message += f"➖ <b>Removed ({len(change['removed'])}):</b>\n"
                    for target in change['removed'][:10]:
                        message += f"• <code>{target}</code>\n"
                    if len(change['removed']) > 10:
                        message += f"... and {len(change['removed']) - 10} more\n"
            
            if change.get('url'):
                message += f"\n🔗 <a href='{change['url']}'>View Program</a>"
            
            try:
                url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
                payload = {
                    "chat_id": self.telegram_chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                }
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                print(f"✓ Telegram notification sent for {change['program']}")
                time.sleep(1)
            except Exception as e:
                print(f"✗ Error sending Telegram notification: {e}")

    def run(self):
        """Main monitoring loop"""
        print(f"🚀 Bug Bounty Monitor started at {datetime.now()}")
        print(f"Monitoring platforms: {', '.join(self.platforms)}")
        print("-" * 60)
        
        all_changes = []
        
        for platform in self.platforms:
            print(f"📡 Checking {platform}...")
            current_data = self.fetch_program_data(platform)
            
            if current_data:
                changes = self.compare_programs(platform, current_data)
                if changes:
                    print(f"  ✓ Found {len(changes)} program(s) with changes")
                    all_changes.extend(changes)
                else:
                    print(f"  • No changes detected")
            else:
                print(f"  ✗ Failed to fetch data")
            
            time.sleep(2)  # Be nice to GitHub
        
        # Send notifications
        if all_changes:
            print(f"\n📬 Sending notifications for {len(all_changes)} change(s)...")
            self.send_discord_notification(all_changes)
            self.send_telegram_notification(all_changes)
            print(f"✓ Notifications sent successfully")
        else:
            print("\n✓ No changes detected across all platforms")
        
        # Save state
        self.save_state(self.previous_state)
        print(f"💾 State saved\n")

def main():
    # Configuration - Set your webhooks here
    DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK', '')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
    
    if not DISCORD_WEBHOOK and not TELEGRAM_BOT_TOKEN:
        print("⚠️  Warning: No notification endpoints configured!")
        print("Set DISCORD_WEBHOOK or TELEGRAM_BOT_TOKEN environment variables")
        print("Example:")
        print("  export DISCORD_WEBHOOK='https://discord.com/api/webhooks/...'")
        print("  export TELEGRAM_BOT_TOKEN='123456:ABC-DEF...'")
        print("  export TELEGRAM_CHAT_ID='123456789'")
        return
    
    monitor = BountyMonitor(
        discord_webhook=DISCORD_WEBHOOK,
        telegram_bot_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID
    )
    
    monitor.run()

if __name__ == "__main__":
    main()
