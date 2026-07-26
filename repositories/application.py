"""Canonical repository registry for v19.2.0.

The registry owns permanent application domains while exact-key document and
event adapters keep legacy modules operational during the staged migration.
"""
from __future__ import annotations

from repositories.base import (
    DocumentRepository,
    EventRepository,
    JsonRepository,
    LegacyDocumentRepository,
    LegacyEventRepository,
)
from services.storage_service import StorageService, get_storage_service


class ReportRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("reports", storage=storage, id_field="run_id")
class PortfolioRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("portfolios", storage=storage, id_field="portfolio_id")
class TradeRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("trades", storage=storage, id_field="trade_id")
class TaskRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("tasks", storage=storage, id_field="task_id")
class ApprovalRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("approvals", storage=storage, id_field="approval_id")
class SourceHealthRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("source_health", storage=storage, id_field="source_id")
class SchedulerRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("scheduler_jobs", storage=storage, id_field="job_id")
class RunTraceRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("run_traces", storage=storage, id_field="trace_id")
class ConfigurationRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("configurations", storage=storage, id_field="config_id")
class LearningRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("learning_records", storage=storage, id_field="learning_id")
class ModelStateRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("model_state", storage=storage, id_field="model_id")
class NotificationRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("notifications", storage=storage, id_field="notification_id")
class StrategyVersionRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("strategy_versions", storage=storage, id_field="version_id")
class MarketSnapshotRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("market_snapshots", storage=storage, id_field="snapshot_id")
class StrategyDecisionRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("strategy_decisions", storage=storage, id_field="decision_id")
class StrategyRunRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("strategy_runs", storage=storage, id_field="strategy_run_id")
class StrategyAccountRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("strategy_accounts", storage=storage, id_field="account_id")
class StrategyOrderRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("strategy_orders", storage=storage, id_field="order_id")
class StrategyFillRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("strategy_fills", storage=storage, id_field="fill_id")
class StrategyAccountSnapshotRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("strategy_account_snapshots", storage=storage, id_field="account_snapshot_id")
class ActivationAnalysisRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("activation_analyses", storage=storage, id_field="analysis_id")
class EvaluationExportRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("evaluation_exports", storage=storage, id_field="export_id")
class StrategyLabExperimentRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("strategy_lab_experiments", storage=storage, id_field="experiment_id")
class StrategyLabRunRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("strategy_lab_runs", storage=storage, id_field="lab_run_id")
class StrategyLabApprovalRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("strategy_lab_approvals", storage=storage, id_field="approval_id")
class StrategyOutcomeRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("strategy_outcomes", storage=storage, id_field="outcome_id")
class StrategyProductionBindingRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("strategy_production_bindings", storage=storage, id_field="binding_id")
class StrategyPromotionRepository(JsonRepository):
    def __init__(self, storage=None): super().__init__("strategy_promotions", storage=storage, id_field="promotion_id")
class StrategyEventRepository(EventRepository):
    def __init__(self, storage=None): super().__init__("strategy_events", storage=storage)
class OperationalEventRepository(EventRepository):
    def __init__(self, storage=None): super().__init__("operational_events", storage=storage)
class AuditEventRepository(EventRepository):
    def __init__(self, storage=None): super().__init__("audit_events", storage=storage)


class RepositoryRegistry:
    def __init__(self, storage: StorageService | None = None):
        storage = storage or get_storage_service()
        self.storage = storage
        self.documents = LegacyDocumentRepository(storage=storage)
        self.events = LegacyEventRepository(storage=storage)
        self.settings = DocumentRepository("settings", storage=storage)
        self.reports = ReportRepository(storage)
        self.portfolios = PortfolioRepository(storage)
        self.trades = TradeRepository(storage)
        self.tasks = TaskRepository(storage)
        self.approvals = ApprovalRepository(storage)
        self.source_health = SourceHealthRepository(storage)
        self.scheduler = SchedulerRepository(storage)
        self.run_traces = RunTraceRepository(storage)
        self.configurations = ConfigurationRepository(storage)
        self.learning = LearningRepository(storage)
        self.model_state = ModelStateRepository(storage)
        self.notifications = NotificationRepository(storage)
        self.strategy_versions = StrategyVersionRepository(storage)
        self.market_snapshots = MarketSnapshotRepository(storage)
        self.strategy_decisions = StrategyDecisionRepository(storage)
        self.strategy_runs = StrategyRunRepository(storage)
        self.strategy_accounts = StrategyAccountRepository(storage)
        self.strategy_orders = StrategyOrderRepository(storage)
        self.strategy_fills = StrategyFillRepository(storage)
        self.strategy_account_snapshots = StrategyAccountSnapshotRepository(storage)
        self.activation_analyses = ActivationAnalysisRepository(storage)
        self.evaluation_exports = EvaluationExportRepository(storage)
        self.strategy_lab_experiments = StrategyLabExperimentRepository(storage)
        self.strategy_lab_runs = StrategyLabRunRepository(storage)
        self.strategy_lab_approvals = StrategyLabApprovalRepository(storage)
        self.strategy_outcomes = StrategyOutcomeRepository(storage)
        self.strategy_production_bindings = StrategyProductionBindingRepository(storage)
        self.strategy_promotions = StrategyPromotionRepository(storage)
        self.strategy_events = StrategyEventRepository(storage)
        self.operational_events = OperationalEventRepository(storage)
        self.audit_events = AuditEventRepository(storage)

    def domain_names(self) -> tuple[str, ...]:
        return (
            "settings", "reports", "portfolios", "trades", "tasks", "approvals",
            "source_health", "scheduler", "run_traces", "configurations",
            "learning", "model_state", "notifications", "strategy_versions", "market_snapshots",
            "strategy_decisions", "strategy_runs", "strategy_accounts", "strategy_orders", "strategy_fills",
            "strategy_account_snapshots", "activation_analyses", "evaluation_exports",
            "strategy_lab_experiments", "strategy_lab_runs", "strategy_lab_approvals", "strategy_outcomes",
            "strategy_production_bindings", "strategy_promotions",
            "strategy_events", "operational_events", "audit_events",
        )


_default_registry: RepositoryRegistry | None = None


def get_repository_registry(storage: StorageService | None = None) -> RepositoryRegistry:
    global _default_registry
    if storage is not None:
        return RepositoryRegistry(storage)
    if _default_registry is None:
        _default_registry = RepositoryRegistry()
    return _default_registry
