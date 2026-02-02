"""
FinBERT sentiment analysis model
Loads and caches ProsusAI/finbert for financial sentiment classification
"""

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from typing import Dict, Tuple, List
import logging

logger = logging.getLogger(__name__)

class SentimentClassifier:
    """FinBERT-based sentiment classifier"""
    
    def __init__(self, model_name: str = 'ProsusAI/finbert'):
        """
        Initialize classifier with FinBERT model
        Model is loaded once and cached in memory
        """
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        self.labels = ['positive', 'negative', 'neutral']
        
    def load_model(self):
        """Load model and tokenizer (called once at startup)"""
        if self.model is not None:
            return  # Already loaded
        
        logger.info(f"Loading model {self.model_name}...")
        
        # Load tokenizer and model
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        
        # Set to evaluation mode
        self.model.eval()
        
        logger.info(f"Model {self.model_name} loaded successfully")
    
    def classify(self, text: str) -> Tuple[str, float]:
        """
        Classify sentiment of text
        
        Args:
            text: Input text (title + summary)
            
        Returns:
            Tuple of (sentiment, confidence_score)
            sentiment: 'positive', 'negative', or 'neutral'
            confidence_score: 0.0 to 1.0
        """
        # Ensure model is loaded
        if self.model is None:
            self.load_model()
        
        try:
            # Tokenize input (truncate to 512 tokens max)
            inputs = self.tokenizer(
                text,
                return_tensors='pt',
                truncation=True,
                max_length=512,
                padding=True
            )
            
            # Run inference (no gradient computation needed)
            with torch.no_grad():
                outputs = self.model(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
            
            # Get prediction and confidence
            confidence, pred_idx = torch.max(predictions, dim=1)
            sentiment = self.labels[pred_idx.item()]
            score = confidence.item()
            
            return sentiment, score
            
        except Exception as e:
            logger.error(f"Classification error: {e}")
            # Return neutral sentiment with low confidence as fallback
            return 'neutral', 0.0
    
    def classify_batch(self, texts: List[str]) -> List[Tuple[str, float]]:
        """
        Classify multiple texts in batch for efficiency
        
        Args:
            texts: List of input texts
            
        Returns:
            List of (sentiment, score) tuples
        """
        # Ensure model is loaded
        if self.model is None:
            self.load_model()
        
        try:
            # Tokenize all texts
            inputs = self.tokenizer(
                texts,
                return_tensors='pt',
                truncation=True,
                max_length=512,
                padding=True
            )
            
            # Run batch inference
            with torch.no_grad():
                outputs = self.model(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
            
            # Extract predictions for each text
            results = []
            for i in range(len(texts)):
                confidence, pred_idx = torch.max(predictions[i], dim=0)
                sentiment = self.labels[pred_idx.item()]
                score = confidence.item()
                results.append((sentiment, score))
            
            return results
            
        except Exception as e:
            logger.error(f"Batch classification error: {e}")
            # Return neutral fallback for all texts
            return [('neutral', 0.0) for _ in texts]
