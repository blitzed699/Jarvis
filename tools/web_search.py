import requests
import urllib.parse
from typing import Dict, Any
from .base import BaseTool


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for current information. Params: query (str)"

    def run(self, query: str) -> Dict[str, Any]:
        try:
            # DuckDuckGo lite HTML search (no API key needed)
            encoded = urllib.parse.quote(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            # Extract results from HTML
            results = self._parse_results(response.text)
            
            return {
                "success": True,
                "result": {
                    "query": query,
                    "results": results[:5],  # Top 5
                    "total_found": len(results)
                }
            }
        except Exception as e:
            return {"success": False, "result": str(e)}
    
    def _parse_results(self, html: str) -> list:
        """Extract search results from DuckDuckGo HTML."""
        import re
        results = []
        
        # DuckDuckGo lite result pattern
        pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)">([^<]+)</a>'
        matches = re.findall(pattern, html)
        
        for url, title in matches:
            # Clean up redirects
            if "/l/?" in url:
                # Extract actual URL from DuckDuckGo redirect
                udd = re.search(r'uddg=([^&]+)', url)
                if udd:
                    import urllib.parse
                    url = urllib.parse.unquote(udd.group(1))
            
            results.append({"title": title.strip(), "url": url})
        
        return results
