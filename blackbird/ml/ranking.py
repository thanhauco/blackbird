"""
Learning to Rank Model

Implements machine learning-based ranking for search results.
Uses gradient boosting or neural ranking models.
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
import pickle
import structlog

logger = structlog.get_logger()

# Try to import ML libraries
try:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available, using simple ranking")


@dataclass
class RankingFeatures:
    """
    Features used for ranking a search result.
    """
    doc_id: str
    
    # Text matching features
    ngram_score: float = 0.0
    semantic_score: float = 0.0
    bm25_score: float = 0.0
    
    # Match quality
    exact_match: bool = False
    prefix_match: bool = False
    symbol_match: bool = False
    matched_ngrams: int = 0
    query_coverage: float = 0.0
    
    # Document features
    file_length: int = 0
    num_symbols: int = 0
    language_match: bool = False
    
    # Popularity features
    repo_stars: int = 0
    file_imports: int = 0
    
    # Freshness
    days_since_update: int = 0
    
    # Click-through data
    historical_ctr: float = 0.0
    
    def to_vector(self) -> np.ndarray:
        """Convert to feature vector"""
        return np.array([
            self.ngram_score,
            self.semantic_score,
            self.bm25_score,
            float(self.exact_match),
            float(self.prefix_match),
            float(self.symbol_match),
            self.matched_ngrams,
            self.query_coverage,
            np.log1p(self.file_length),
            self.num_symbols,
            float(self.language_match),
            np.log1p(self.repo_stars),
            np.log1p(self.file_imports),
            np.log1p(self.days_since_update + 1),
            self.historical_ctr
        ])
    
    @staticmethod
    def feature_names() -> List[str]:
        return [
            "ngram_score", "semantic_score", "bm25_score",
            "exact_match", "prefix_match", "symbol_match",
            "matched_ngrams", "query_coverage", "file_length_log",
            "num_symbols", "language_match", "repo_stars_log",
            "file_imports_log", "days_since_update_log", "historical_ctr"
        ]


@dataclass
class RankingLabel:
    """Label for training data"""
    doc_id: str
    relevance: int  # 0=not relevant, 1=somewhat, 2=relevant, 3=highly relevant
    clicked: bool = False
    dwell_time: float = 0.0  # seconds spent on result


class LearningToRank:
    """
    Learning to rank model for search results.
    
    Uses gradient boosted trees for pointwise ranking.
    Can be extended to pairwise (RankNet) or listwise (LambdaMART).
    """
    
    def __init__(
        self,
        model_path: Optional[Path] = None,
        n_estimators: int = 100,
        learning_rate: float = 0.1
    ):
        """
        Initialize the ranking model.
        """
        self.model_path = model_path
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        
        self.model = None
        self.scaler = None
        
        if SKLEARN_AVAILABLE:
            self.model = GradientBoostingClassifier(
                n_estimators=n_estimators,
                learning_rate=learning_rate,
                max_depth=5,
                random_state=42
            )
            self.scaler = StandardScaler()
        
        # Load existing model if available
        if model_path and model_path.exists():
            self.load(model_path)
    
    def train(
        self,
        features: List[RankingFeatures],
        labels: List[RankingLabel]
    ):
        """
        Train the ranking model.
        
        Args:
            features: List of feature vectors for each document
            labels: Relevance labels for each document
        """
        if not SKLEARN_AVAILABLE:
            logger.warning("Cannot train: sklearn not available")
            return
        
        # Build training data
        X = np.array([f.to_vector() for f in features])
        y = np.array([l.relevance > 0 for l in labels])  # Binary relevance
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Train model
        self.model.fit(X_scaled, y)
        
        logger.info(
            "Trained ranking model",
            n_samples=len(features),
            n_positive=sum(y)
        )
    
    def predict(self, features: List[RankingFeatures]) -> List[float]:
        """
        Predict relevance scores for results.
        
        Returns:
            List of relevance scores (higher = more relevant)
        """
        if not self.model or not SKLEARN_AVAILABLE:
            # Fallback to simple weighted sum
            return [self._simple_score(f) for f in features]
        
        X = np.array([f.to_vector() for f in features])
        X_scaled = self.scaler.transform(X)
        
        # Use probability of positive class as score
        scores = self.model.predict_proba(X_scaled)[:, 1]
        
        return list(scores)
    
    def _simple_score(self, features: RankingFeatures) -> float:
        """Simple fallback scoring without ML"""
        score = 0.0
        
        # Base scores
        score += features.ngram_score * 0.4
        score += features.semantic_score * 0.3
        score += features.bm25_score * 0.2
        
        # Bonuses
        if features.exact_match:
            score += 0.3
        if features.symbol_match:
            score += 0.2
        if features.prefix_match:
            score += 0.1
        
        # CTR signal
        score += features.historical_ctr * 0.1
        
        return score
    
    def rank(
        self,
        features: List[RankingFeatures]
    ) -> List[Tuple[str, float]]:
        """
        Rank documents by predicted relevance.
        
        Returns:
            List of (doc_id, score) tuples sorted by score
        """
        scores = self.predict(features)
        
        ranked = [
            (features[i].doc_id, scores[i])
            for i in range(len(features))
        ]
        
        ranked.sort(key=lambda x: x[1], reverse=True)
        
        return ranked
    
    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance from the model"""
        if not self.model or not hasattr(self.model, 'feature_importances_'):
            return {}
        
        names = RankingFeatures.feature_names()
        importances = self.model.feature_importances_
        
        return dict(zip(names, importances))
    
    def save(self, path: Optional[Path] = None):
        """Save the model to disk"""
        path = path or self.model_path
        if not path:
            return
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "wb") as f:
            pickle.dump({
                "model": self.model,
                "scaler": self.scaler
            }, f)
        
        logger.info("Saved ranking model", path=str(path))
    
    def load(self, path: Optional[Path] = None):
        """Load the model from disk"""
        path = path or self.model_path
        if not path or not path.exists():
            return
        
        with open(path, "rb") as f:
            data = pickle.load(f)
            self.model = data["model"]
            self.scaler = data["scaler"]
        
        logger.info("Loaded ranking model", path=str(path))


class ClickModel:
    """
    Click model for learning from user interactions.
    
    Tracks clicks and uses them to improve ranking.
    """
    
    def __init__(self):
        # Query -> doc_id -> stats
        self.click_stats: Dict[str, Dict[str, Dict[str, Any]]] = {}
    
    def record_impression(
        self,
        query: str,
        results: List[str],  # doc_ids in order shown
        position_bias: bool = True
    ):
        """Record search result impressions"""
        if query not in self.click_stats:
            self.click_stats[query] = {}
        
        for pos, doc_id in enumerate(results):
            if doc_id not in self.click_stats[query]:
                self.click_stats[query][doc_id] = {
                    "impressions": 0,
                    "clicks": 0,
                    "total_position": 0
                }
            
            stats = self.click_stats[query][doc_id]
            stats["impressions"] += 1
            stats["total_position"] += pos
    
    def record_click(
        self,
        query: str,
        doc_id: str,
        position: int,
        dwell_time: float = 0
    ):
        """Record a click on a search result"""
        if query not in self.click_stats:
            self.click_stats[query] = {}
        
        if doc_id not in self.click_stats[query]:
            self.click_stats[query][doc_id] = {
                "impressions": 1,
                "clicks": 0,
                "total_position": position
            }
        
        self.click_stats[query][doc_id]["clicks"] += 1
    
    def get_ctr(self, query: str, doc_id: str) -> float:
        """Get click-through rate for a query-doc pair"""
        if query not in self.click_stats:
            return 0.0
        
        if doc_id not in self.click_stats[query]:
            return 0.0
        
        stats = self.click_stats[query][doc_id]
        if stats["impressions"] == 0:
            return 0.0
        
        return stats["clicks"] / stats["impressions"]
    
    def get_position_adjusted_ctr(self, query: str, doc_id: str) -> float:
        """
        Get position-adjusted CTR.
        
        Accounts for the fact that lower positions get fewer clicks.
        """
        ctr = self.get_ctr(query, doc_id)
        
        if query not in self.click_stats or doc_id not in self.click_stats[query]:
            return 0.0
        
        stats = self.click_stats[query][doc_id]
        avg_position = stats["total_position"] / max(stats["impressions"], 1)
        
        # Position bias correction (simplified)
        # Lower positions get a boost
        position_factor = 1.0 / (1.0 + 0.1 * avg_position)
        
        return ctr / position_factor


class PersonalizedRanker:
    """
    Personalized ranking based on user preferences.
    """
    
    def __init__(self):
        # User -> preferences
        self.user_prefs: Dict[str, Dict[str, Any]] = {}
    
    def update_preferences(
        self,
        user_id: str,
        language: Optional[str] = None,
        repos: Optional[List[str]] = None
    ):
        """Update user preferences based on interactions"""
        if user_id not in self.user_prefs:
            self.user_prefs[user_id] = {
                "languages": {},
                "repos": {},
                "file_types": {}
            }
        
        if language:
            prefs = self.user_prefs[user_id]["languages"]
            prefs[language] = prefs.get(language, 0) + 1
    
    def get_personalization_boost(
        self,
        user_id: str,
        language: str,
        repo_id: str
    ) -> float:
        """Get personalization boost for a result"""
        if user_id not in self.user_prefs:
            return 0.0
        
        prefs = self.user_prefs[user_id]
        boost = 0.0
        
        # Language preference
        lang_prefs = prefs.get("languages", {})
        total_lang = sum(lang_prefs.values())
        if total_lang > 0:
            boost += lang_prefs.get(language, 0) / total_lang * 0.1
        
        # Repo preference
        repo_prefs = prefs.get("repos", {})
        total_repo = sum(repo_prefs.values())
        if total_repo > 0:
            boost += repo_prefs.get(repo_id, 0) / total_repo * 0.1
        
        return boost
