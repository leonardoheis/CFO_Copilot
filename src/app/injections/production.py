from dependency_injector import containers, providers

from app.data.companies import CompanyRegistry
from app.data.sources import (
    AlphaVantageSource,
    FredSource,
    SecEdgarSource,
    YfinanceSource,
)
from app.data.sources_bundle import IngestionSources
from app.services import PredictionService, TrainingService
from app.settings import Settings


class Container(containers.DeclarativeContainer):
    prediction_service = providers.Factory(PredictionService)
    training_service = providers.Factory(TrainingService)

    company_registry = providers.Singleton(
        CompanyRegistry.from_path,
        Settings.COMPANY_REGISTRY_PATH,
    )

    fred_source = providers.Factory(FredSource, api_key=Settings.FRED_API_KEY)
    yfinance_source = providers.Factory(YfinanceSource, registry=company_registry)
    sec_edgar_source = providers.Factory(
        SecEdgarSource,
        user_agent=Settings.SEC_USER_AGENT,
        registry=company_registry,
    )
    alpha_vantage_source = providers.Factory(
        AlphaVantageSource,
        api_key=Settings.ALPHA_VANTAGE_API_KEY,
        cache_directory=Settings.DATA_DIRECTORY / "raw" / "alpha_vantage",
    )

    ingestion_sources = providers.Factory(
        IngestionSources.from_sources,
        fred=fred_source,
        yfinance=yfinance_source,
        sec_edgar=sec_edgar_source,
        registry=company_registry,
        alpha_vantage=alpha_vantage_source if Settings.ALPHA_VANTAGE_API_KEY else None,
    )
