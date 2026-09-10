from dependency_injector import containers, providers

from app.data.companies import CompanyRegistry
from app.data.sources import FredSource, SecEdgarSource, YfinanceSource
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

    ingestion_sources = providers.Factory(
        IngestionSources,
        fred=fred_source,
        yfinance=yfinance_source,
        sec_edgar=sec_edgar_source,
        registry=company_registry,
    )
