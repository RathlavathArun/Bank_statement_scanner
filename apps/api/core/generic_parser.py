"""
Generic bank statement parser - fallback for unsupported banks.
Uses heuristic-based column detection for unknown bank formats.
"""
import re
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal
import pandas as pd

logger = logging.getLogger(__name__)


class ColumnDetector:
    """Detect transaction columns using heuristics."""
    
    # Regex patterns for column detection
    DATE_PATTERNS = [
        r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # DD/MM/YYYY or MM/DD/YYYY
        r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',    # YYYY-MM-DD
    ]
    
    AMOUNT_PATTERNS = [
        r'\d{1,3}(?:[,.]?\d{3})*(?:[.,]\d{2})?',  # Currency amount
    ]
    
    DEBIT_KEYWORDS = ['debit', 'withdrawal', 'payment', 'spent', 'dr.', 'dr', 'out']
    CREDIT_KEYWORDS = ['credit', 'deposit', 'received', 'income', 'cr.', 'cr', 'in']
    
    def __init__(self):
        self.confidence_scores = {}
    
    def detect_columns(self, df: pd.DataFrame) -> Dict[str, int]:
        """
        Detect transaction columns from DataFrame.
        
        Returns:
            Dict mapping column names to column indices
        """
        detected = {}
        headers = df.columns.tolist()
        
        # Try to find each column type
        detected['date'] = self._find_date_column(df)
        detected['narration'] = self._find_narration_column(df)
        detected['debit'] = self._find_debit_column(df)
        detected['credit'] = self._find_credit_column(df)
        detected['balance'] = self._find_balance_column(df)
        
        return {k: v for k, v in detected.items() if v is not None}
    
    def _find_date_column(self, df: pd.DataFrame) -> Optional[int]:
        """Find date column."""
        best_score = 0
        best_col = None
        
        for col_idx, col_name in enumerate(df.columns):
            score = 0
            
            # Check column name
            if any(word in str(col_name).lower() for word in ['date', 'dt', 'day', 'posted']):
                score += 30
            
            # Check values
            sample = df.iloc[:10, col_idx].dropna()
            for val in sample:
                val_str = str(val).strip()
                for pattern in self.DATE_PATTERNS:
                    if re.search(pattern, val_str):
                        score += 10
            
            if score > best_score:
                best_score = score
                best_col = col_idx
        
        if best_score > 20:
            self.confidence_scores['date'] = round(best_score / 40, 2)
            return best_col
        
        return None
    
    def _find_narration_column(self, df: pd.DataFrame) -> Optional[int]:
        """Find narration/description column."""
        best_score = 0
        best_col = None
        
        for col_idx, col_name in enumerate(df.columns):
            score = 0
            
            # Check column name
            if any(word in str(col_name).lower() for word in ['narration', 'description', 'ref', 'detail', 'memo']):
                score += 30
            
            # Text columns typically have longer values
            sample = df.iloc[:10, col_idx].dropna()
            avg_length = sum(len(str(v)) for v in sample) / max(len(sample), 1)
            
            if avg_length > 15:  # Narration typically longer
                score += 20
            
            if score > best_score:
                best_score = score
                best_col = col_idx
        
        if best_score > 15:
            self.confidence_scores['narration'] = round(best_score / 50, 2)
            return best_col
        
        return None
    
    def _find_debit_column(self, df: pd.DataFrame) -> Optional[int]:
        """Find debit/withdrawal column."""
        return self._find_amount_column(df, 'debit')
    
    def _find_credit_column(self, df: pd.DataFrame) -> Optional[int]:
        """Find credit/deposit column."""
        return self._find_amount_column(df, 'credit')
    
    def _find_amount_column(self, df: pd.DataFrame, amount_type: str) -> Optional[int]:
        """Find amount column for debit or credit."""
        best_score = 0
        best_col = None
        keywords = self.DEBIT_KEYWORDS if amount_type == 'debit' else self.CREDIT_KEYWORDS
        
        for col_idx, col_name in enumerate(df.columns):
            score = 0
            
            # Check column name
            col_name_lower = str(col_name).lower()
            if any(word in col_name_lower for word in keywords):
                score += 30
            
            # Check values are numeric
            sample = df.iloc[:10, col_idx].dropna()
            numeric_count = 0
            
            for val in sample:
                val_str = str(val).strip()
                try:
                    float(val_str.replace(',', '').replace('₹', ''))
                    numeric_count += 1
                except ValueError:
                    pass
            
            numeric_ratio = numeric_count / max(len(sample), 1)
            if numeric_ratio > 0.7:
                score += 20
            
            if score > best_score:
                best_score = score
                best_col = col_idx
        
        if best_score > 15:
            key = f'{amount_type}_confidence'
            self.confidence_scores[key] = round(best_score / 50, 2)
            return best_col
        
        return None
    
    def _find_balance_column(self, df: pd.DataFrame) -> Optional[int]:
        """Find balance column."""
        best_score = 0
        best_col = None
        
        for col_idx, col_name in enumerate(df.columns):
            score = 0
            
            # Check column name
            if any(word in str(col_name).lower() for word in ['balance', 'closing', 'running', 'bal']):
                score += 30
            
            # Balance column typically numeric and all non-null
            sample = df.iloc[:10, col_idx].dropna()
            numeric_count = 0
            
            for val in sample:
                val_str = str(val).strip()
                try:
                    float(val_str.replace(',', '').replace('₹', ''))
                    numeric_count += 1
                except ValueError:
                    pass
            
            numeric_ratio = numeric_count / max(len(sample), 1)
            if numeric_ratio > 0.9:
                score += 20
            
            if score > best_score:
                best_score = score
                best_col = col_idx
        
        if best_score > 15:
            self.confidence_scores['balance_confidence'] = round(best_score / 50, 2)
            return best_col
        
        return None


class GenericBankParser:
    """Generic parser for unsupported bank formats."""
    
    def __init__(self):
        self.detector = ColumnDetector()
    
    def parse_dataframe(self, df: pd.DataFrame) -> Tuple[List[Dict], Dict]:
        """
        Parse a DataFrame using heuristic column detection.
        
        Returns:
            Tuple of (transactions list, metadata dict)
        """
        if df.empty:
            return [], {}
        
        # Detect columns
        columns = self.detector.detect_columns(df)
        
        if not columns:
            logger.warning("Could not detect any columns")
            return [], {"error": "Could not detect transaction columns"}
        
        # Extract transactions
        transactions = []
        
        for idx, row in df.iterrows():
            try:
                txn = self._extract_transaction(row, columns, idx)
                if txn:
                    transactions.append(txn)
            except Exception as e:
                logger.warning(f"Error parsing row {idx}: {e}")
                continue
        
        # Metadata
        metadata = {
            "parser_type": "generic",
            "detected_columns": columns,
            "confidence_scores": self.detector.confidence_scores,
            "total_rows_parsed": len(transactions),
            "detection_method": "heuristic",
        }
        
        return transactions, metadata
    
    def _extract_transaction(self, row: pd.Series, columns: Dict[str, int], row_num: int) -> Optional[Dict]:
        """Extract a single transaction from a row."""
        txn = {
            "row_number": row_num + 1,
        }
        
        # Date
        if 'date' in columns:
            date_val = self._parse_date(row.iloc[columns['date']])
            if date_val:
                txn['date'] = date_val
        
        # Narration
        if 'narration' in columns:
            txn['narration'] = str(row.iloc[columns['narration']]).strip()
        
        # Debit
        if 'debit' in columns:
            debit_val = self._parse_amount(row.iloc[columns['debit']])
            if debit_val:
                txn['debit'] = debit_val
        
        # Credit
        if 'credit' in columns:
            credit_val = self._parse_amount(row.iloc[columns['credit']])
            if credit_val:
                txn['credit'] = credit_val
        
        # Balance
        if 'balance' in columns:
            balance_val = self._parse_amount(row.iloc[columns['balance']])
            if balance_val:
                txn['balance'] = balance_val
        
        # Confidence
        avg_confidence = sum(self.detector.confidence_scores.values()) / len(self.detector.confidence_scores) if self.detector.confidence_scores else 0
        txn['generic_parser_confidence'] = round(avg_confidence, 3)
        
        return txn if ('date' in txn or 'narration' in txn) else None
    
    def _parse_date(self, value) -> Optional[str]:
        """Parse date value."""
        if pd.isna(value):
            return None
        
        val_str = str(value).strip()
        
        # Try common date formats
        formats = ['%d/%m/%Y', '%d/%m/%y', '%d-%m-%Y', '%d-%m-%y', '%Y-%m-%d', '%m/%d/%Y']
        
        for fmt in formats:
            try:
                parsed = datetime.strptime(val_str, fmt)
                return parsed.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        return None
    
    def _parse_amount(self, value) -> Optional[Decimal]:
        """Parse amount value."""
        if pd.isna(value):
            return None
        
        val_str = str(value).strip()
        
        # Remove currency symbols and spaces
        val_str = val_str.replace('₹', '').replace('$', '').replace(',', '').strip()
        
        try:
            return Decimal(val_str)
        except:
            return None


def parse_generic_statement(df: pd.DataFrame) -> Tuple[List[Dict], Dict]:
    """
    Parse statement with generic parser.
    
    Args:
        df: Pandas DataFrame with bank statement
    
    Returns:
        Tuple of (transactions, metadata)
    """
    parser = GenericBankParser()
    return parser.parse_dataframe(df)
