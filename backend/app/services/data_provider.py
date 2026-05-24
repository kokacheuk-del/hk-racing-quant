"""
Data Provider 抽象層 — 狡兔三窟架構

目前實現：
  - GraphQLProvider：直接調用 HKJC GraphQL API（預設，最穩）

預留但現在不建：
  - BrowserProvider：Coze Browser Use / Playwright 模擬真人拿 Token
  - CacheProvider：Supabase / Redis 快取 + 過期重抓

切換方式：改環境變數 DATA_PROVIDER 即可，路由層無需改動。
"""
import os
import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import date

logger = logging.getLogger(__name__)


class DataProvider(ABC):
    """數據源抽象介面 — 所有數據源必須實現這些方法"""

    @abstractmethod
    def get_race_meetings(
        self, race_date: Optional[str] = None, venue_code: Optional[str] = None
    ) -> Optional[List[Dict]]:
        """獲取賽事日列表（含排位表、出賽馬）"""
        ...

    @abstractmethod
    def get_race_odds(
        self,
        race_no: int = 1,
        odds_types: Optional[List[str]] = None,
        date: Optional[str] = None,
        venue_code: Optional[str] = None,
    ) -> Optional[Dict]:
        """獲取賠率數據（獨贏/位置/QIN 等）"""
        ...

    @abstractmethod
    def get_race_pools(
        self,
        race_no: int = 1,
        odds_types: Optional[List[str]] = None,
        date: Optional[str] = None,
        venue_code: Optional[str] = None,
    ) -> Optional[Dict]:
        """獲取彩池投注額"""
        ...

    @abstractmethod
    def fetch_results(self, race_date: date) -> Any:
        """獲取歷史賽果"""
        ...

    def health_check(self) -> Dict[str, Any]:
        """健康檢查 — 子類可覆寫"""
        return {"provider": self.name, "status": "ok"}

    @property
    def name(self) -> str:
        return self.__class__.__name__


class GraphQLProvider(DataProvider):
    """
    HKJC GraphQL API 數據源（預設）。
    直接調用 info.cld.hkjc.com/graphql/base/。
    優勢：快速、穩定、數據量小。
    風險：未來可能加動態 Token 驗證。
    """

    def __init__(self):
        from app.scraper.hkjc_fetcher import HKJCGraphQLClient, HKJCDataFetcher
        self._gql = HKJCGraphQLClient()
        self._fetcher = HKJCDataFetcher()
        logger.info("DataProviver initialized: GraphQLProvider")

    def get_race_meetings(
        self, race_date: Optional[str] = None, venue_code: Optional[str] = None
    ) -> Optional[List[Dict]]:
        return self._gql.get_race_meetings(race_date=race_date, venue_code=venue_code)

    def get_race_odds(
        self,
        race_no: int = 1,
        odds_types: Optional[List[str]] = None,
        date: Optional[str] = None,
        venue_code: Optional[str] = None,
    ) -> Optional[Dict]:
        return self._gql.get_race_odds(
            race_no=race_no, odds_types=odds_types, date=date, venue_code=venue_code
        )

    def get_race_pools(
        self,
        race_no: int = 1,
        odds_types: Optional[List[str]] = None,
        date: Optional[str] = None,
        venue_code: Optional[str] = None,
    ) -> Optional[Dict]:
        return self._gql.get_race_pools(
            race_no=race_no, odds_types=odds_types, date=date, venue_code=venue_code
        )

    def fetch_results(self, race_date: date) -> Any:
        return self._fetcher.fetch_results(race_date)

    def health_check(self) -> Dict[str, Any]:
        try:
            data = self._gql.get_active_meetings()
            return {
                "provider": self.name,
                "status": "ok",
                "active_meetings": len(data) if data else 0,
            }
        except Exception as e:
            return {"provider": self.name, "status": "error", "error": str(e)}


# ═══════════════════════════════════════════════
#  Provider Factory
# ═══════════════════════════════════════════════

_PROVIDERS = {
    "graphql": GraphQLProvider,
    # 預留：
    # "browser": BrowserProvider,
    # "cache": CacheProvider,
}

_provider_instance: Optional[DataProvider] = None


def get_provider() -> DataProvider:
    """
    取得當前數據源（單例）。
    通過環境變數 DATA_PROVIDER 切換，預設 graphql。
    """
    global _provider_instance
    if _provider_instance is None:
        provider_name = os.getenv("DATA_PROVIDER", "graphql").lower()
        if provider_name not in _PROVIDERS:
            logger.warning(
                f"Unknown DATA_PROVIDER '{provider_name}', falling back to 'graphql'. "
                f"Available: {list(_PROVIDERS.keys())}"
            )
            provider_name = "graphql"
        _provider_instance = _PROVIDERS[provider_name]()
        logger.info(f"Using DataProvider: {provider_name}")
    return _provider_instance


def reset_provider():
    """重置 provider（用於切換數據源後重新初始化）"""
    global _provider_instance
    _provider_instance = None
