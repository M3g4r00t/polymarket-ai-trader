import requests
import time
from src.utils.logger import Logger
from src.client import PolymarketClient

class CopyTradingStrategy:
    def __init__(self, settings):
        self.settings = settings
        self.logger = Logger(__name__)
        self.client = PolymarketClient()
        self.whale_positions = []

    def scan_whale_positions(self):
        """Identifica posiciones de 'whales' en Polymarket"""
        url = f"https://api.polymarket.com/v1/positions?minSize={self.settings['whale_traders']['min_position']}&limit=100"
        
        try:
            response = requests.get(url)
            self.whale_positions = response.json()['data']
            self.logger.info(f"Found {len(self.whale_positions)} whale positions")
        except Exception as e:
            self.logger.error(f"Error scanning whale positions: {str(e)}")

    def follow_top_traders(self):
        """Replica las posiciones de los traders más exitosos"""
        for position in self.whale_positions[:self.settings['whale_traders']['max_followers']]:
            try:
                self.client.place_order(
                    market_id=position['market_id'],
                    outcome=position['outcome'],
                    amount=position['size'] * 0.01  # 1% de la posición del whale
                )
                self.logger.info(f"Followed whale position: {position['market_id']} {position['outcome']}")
            except Exception as e:
                self.logger.error(f"Error following position {position['market_id']}: {str(e)}")

    def run(self):
        """Ejecuta la estrategia de copy trading"""
        while True:
            self.scan_whale_positions()
            self.follow_top_traders()
            time.sleep(self.settings['whale_traders']['update_interval'])