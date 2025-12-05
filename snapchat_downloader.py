import aiohttp
import asyncio
import re
import json
import hashlib
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
import aiofiles
from pathlib import Path
import time
from urllib.parse import urlparse, unquote

class SnapchatDownloader:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.cache = {}
        self.request_semaphore = asyncio.Semaphore(5)  # Limit concurrent requests
        
    async def fetch_public_content(self, username: str) -> List[Dict]:
        """Fetch public Snapchat stories for a username."""
        url = f"https://story.snapchat.com/s/{username}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        }
        
        try:
            async with self.request_semaphore:
                async with self.session.get(url, headers=headers, timeout=30) as response:
                    if response.status != 200:
                        return []
                    
                    html = await response.text()
                    
                    # Multiple extraction methods for redundancy
                    media_items = []
                    
                    # Method 1: JSON-LD structured data
                    media_items.extend(self._extract_json_ld(html))
                    
                    # Method 2: JavaScript data objects
                    media_items.extend(self._extract_js_data(html))
                    
                    # Method 3: Direct URL patterns
                    media_items.extend(self._extract_direct_urls(html))
                    
                    # Remove duplicates
                    unique_items = []
                    seen_urls = set()
                    for item in media_items:
                        if item['url'] not in seen_urls:
                            seen_urls.add(item['url'])
                            unique_items.append(item)
                    
                    return unique_items[:15]  # Limit to 15 items
                    
        except Exception as e:
            print(f"Error fetching content: {e}")
            return []
    
    def _extract_json_ld(self, html: str) -> List[Dict]:
        """Extract media from JSON-LD structured data."""
        items = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            script_tags = soup.find_all('script', type='application/ld+json')
            
            for script in script_tags:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        for item in data:
                            self._parse_json_item(item, items)
                    elif isinstance(data, dict):
                        self._parse_json_item(data, items)
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass
        return items
    
    def _parse_json_item(self, item: Dict, items_list: List[Dict]):
        """Parse individual JSON item for media."""
        item_type = item.get('@type', '').lower()
        
        if item_type in ['videoobject', 'imageobject']:
            url = item.get('contentUrl') or item.get('url')
            if url and ('http://' in url or 'https://' in url):
                items_list.append({
                    'url': url,
                    'type': 'video' if 'video' in item_type else 'image',
                    'thumbnail': item.get('thumbnailUrl'),
                    'description': item.get('description', '')[:100]
                })
    
    def _extract_js_data(self, html: str) -> List[Dict]:
        """Extract media from JavaScript variables."""
        items = []
        
        # Pattern for window.__INITIAL_STATE__ or similar
        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
            r'window\.__PRELOADED_STATE__\s*=\s*({.*?});',
            r'var\s+__DATA__\s*=\s*({.*?});',
            r'data:\s*({.*?})\s*,\s*error:',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match)
                    items.extend(self._traverse_json_for_media(data))
                except:
                    continue
        
        return items
    
    def _traverse_json_for_media(self, data, depth=0, max_depth=10):
        """Recursively traverse JSON for media URLs."""
        items = []
        
        if depth > max_depth:
            return items
        
        if isinstance(data, dict):
            # Check for media URLs in dictionary
            for key, value in data.items():
                key_lower = key.lower()
                if any(media_key in key_lower for media_key in ['url', 'video', 'image', 'media', 'src']):
                    if isinstance(value, str) and value.startswith('http'):
                        items.append({
                            'url': value,
                            'type': 'video' if 'video' in key_lower else 'image',
                            'source': 'json'
                        })
                elif isinstance(value, (dict, list)):
                    items.extend(self._traverse_json_for_media(value, depth + 1))
        
        elif isinstance(data, list):
            for item in data:
                items.extend(self._traverse_json_for_media(item, depth + 1))
        
        return items
    
    def _extract_direct_urls(self, html: str) -> List[Dict]:
        """Extract media URLs using regex patterns."""
        items = []
        
        # Video URL patterns
        video_patterns = [
            r'"videoUrl":"(https://[^"]+\.mp4[^"]*)"',
            r'src="(https://[^"]+\.mp4[^"]*)"',
            r'data-video-url="(https://[^"]+\.mp4[^"]*)"',
            r'property="og:video" content="(https://[^"]+\.mp4[^"]*)"',
            r'<source[^>]+src="(https://[^"]+\.mp4[^"]*)"',
        ]
        
        # Image URL patterns
        image_patterns = [
            r'"imageUrl":"(https://[^"]+\.jpg[^"]*)"',
            r'src="(https://[^"]+\.jpg[^"]*)"',
            r'data-image-url="(https://[^"]+\.jpg[^"]*)"',
            r'property="og:image" content="(https://[^"]+\.jpg[^"]*)"',
            r'<img[^>]+src="(https://[^"]+\.jpg[^"]*)"',
        ]
        
        for pattern in video_patterns:
            for match in re.findall(pattern, html, re.IGNORECASE):
                items.append({'url': match, 'type': 'video'})
        
        for pattern in image_patterns:
            for match in re.findall(pattern, html, re.IGNORECASE):
                items.append({'url': match, 'type': 'image'})
        
        return items
    
    async def download_media(self, url: str, filename: str) -> Optional[Path]:
        """Download media file with progress tracking."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
            }
            
            async with self.session.get(url, headers=headers, timeout=60) as response:
                if response.status != 200:
                    return None
                
                # Get file extension from URL or Content-Type
                content_type = response.headers.get('Content-Type', '')
                if 'video' in content_type:
                    ext = '.mp4'
                elif 'image' in content_type:
                    ext = '.jpg' if 'jpeg' in content_type else '.png'
                else:
                    # Try to get from URL
                    parsed = urlparse(url)
                    ext = Path(parsed.path).suffix
                    if not ext:
                        ext = '.mp4'  # Default
                
                filepath = Path(config.TEMP_DIR) / f"{filename}{ext}"
                
                # Download in chunks
                async with aiofiles.open(filepath, 'wb') as f:
                    total_size = 0
                    async for chunk in response.content.iter_chunked(8192):
                        if chunk:
                            await f.write(chunk)
                            total_size += len(chunk)
                            
                            # Check size limit
                            if total_size > config.MAX_FILE_SIZE:
                                await f.close()
                                filepath.unlink(missing_ok=True)
                                return None
                
                return filepath if filepath.exists() and filepath.stat().st_size > 0 else None
                
        except Exception as e:
            print(f"Download error: {e}")
            return None
    
    def extract_username_from_url(self, text: str) -> Optional[str]:
        """Extract username from various URL formats."""
        patterns = [
            r'snapchat\.com/add/([a-zA-Z0-9_.-]+)',
            r'snapchat\.com/s/([a-zA-Z0-9_.-]+)',
            r'snapchat\.com/([a-zA-Z0-9_.-]+)',
            r'@([a-zA-Z0-9_.-]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).lower()
        
        # If it looks like a plain username
        if re.match(r'^[a-zA-Z0-9_.-]{3,20}$', text):
            return text.lower()
        
        return None