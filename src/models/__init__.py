"""SQLAlchemy ORM models — import every model so Base.metadata is populated."""

from src.models.topic import (
    TopicalMap,
    PillarTopic,
    TopicCluster,
    SupportingPage,
)
from src.models.keyword import (
    Keyword,
    KeywordCluster,
)
from src.models.content import (
    ContentBrief,
    BlogPost,
    ContentRefresh,
)
from src.models.audit import (
    SiteAudit,
    AuditCheck,
    CoreWebVitals,
)
from src.models.backlink import (
    Backlink,
    BacklinkCheck,
    OutreachCampaign,
    OutreachProspect,
    OutreachEmail,
    EmailTemplate,
)
from src.models.ranking import (
    RankingEntry,
    SERPSnapshot,
    RankingRecord,
    RankingHistory,
    SERPFeature,
    CompetitorRank,
    VisibilityScore,
)
from src.models.report import (
    Report,
    Alert,
)
from src.models.local_seo import (
    LocalBusinessProfile,
    LocalSEOAudit,
    LocalCompetitor,
    CitationEntry,
    LocalKeywordTracking,
)

__all__ = [
    "TopicalMap",
    "PillarTopic",
    "TopicCluster",
    "SupportingPage",
    "Keyword",
    "KeywordCluster",
    "ContentBrief",
    "BlogPost",
    "ContentRefresh",
    "SiteAudit",
    "AuditCheck",
    "CoreWebVitals",
    "Backlink",
    "BacklinkCheck",
    "OutreachCampaign",
    "OutreachProspect",
    "OutreachEmail",
    "EmailTemplate",
    "RankingEntry",
    "SERPSnapshot",
    "RankingRecord",
    "RankingHistory",
    "SERPFeature",
    "CompetitorRank",
    "VisibilityScore",
    "Report",
    "Alert",
    "LocalBusinessProfile",
    "LocalSEOAudit",
    "LocalCompetitor",
    "CitationEntry",
    "LocalKeywordTracking",
]
