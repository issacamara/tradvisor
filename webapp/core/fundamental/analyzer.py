"""
Fundamental Analysis Module
Analyzes financial statements and ratings for long-term investment decisions
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional


class FundamentalAnalyzer:
    """
    Analyze stocks based on financial statements and ratings.
    Provides metrics for passive income and long-term investment decisions.
    """
    
    # Thresholds for passive income investing (from IMPLEMENTATION_PLAN.md)
    THRESHOLDS = {
        'min_dividend_yield': 0.06,  # 6%
        'max_pe_ratio': 15,
        'max_pb_ratio': 1.5,
        'max_payout_ratio': 0.70,  # 70%
        'min_roe': 0.15,  # 15%
        'min_market_cap': 50_000_000_000  # 50B XOF
    }
    
    def __init__(self):
        self.thresholds = self.THRESHOLDS
    
    def calculate_financial_ratios(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate key financial ratios from financial statements.
        
        Args:
            df: DataFrame with financial data (revenue, net_income, total_debt, etc.)
            
        Returns:
            DataFrame with added ratio columns
        """
        result = df.copy()
        
        # Debt-to-Equity Ratio
        if 'total_debt' in result.columns and 'total_equity' in result.columns:
            result['debt_to_equity'] = np.where(
                result['total_equity'] > 0,
                result['total_debt'] / result['total_equity'],
                np.nan
            )
        
        # Return on Equity (ROE)
        if 'net_income' in result.columns and 'total_equity' in result.columns:
            result['roe'] = np.where(
                result['total_equity'] > 0,
                result['net_income'] / result['total_equity'],
                np.nan
            )
        
        # Net Profit Margin
        if 'net_income' in result.columns and 'revenue' in result.columns:
            result['net_margin'] = np.where(
                result['revenue'] > 0,
                result['net_income'] / result['revenue'],
                np.nan
            )
        
        # Current Ratio (liquidity)
        if 'cash_and_cash_equivalents' in result.columns and 'total_debt' in result.columns:
            # Simplified current ratio using cash as proxy
            result['cash_to_debt'] = np.where(
                result['total_debt'] > 0,
                result['cash_and_cash_equivalents'] / result['total_debt'],
                np.nan
            )
        
        return result
    
    def analyze_ratings(self, ratings_df: pd.DataFrame) -> pd.DataFrame:
        """
        Analyze credit ratings for financial stability.
        
        Args:
            ratings_df: DataFrame with rating_short_term and rating_long_term
            
        Returns:
            DataFrame with rating analysis columns
        """
        if ratings_df.empty:
            return ratings_df
        
        result = ratings_df.copy()
        
        # Define rating tiers (higher = better)
        rating_tiers = {
            'AAA': 7, 'AA+': 6.5, 'AA': 6, 'AA-': 5.5,
            'A+': 5, 'A': 4.5, 'A-': 4,
            'BBB+': 3.5, 'BBB': 3, 'BBB-': 2.5,
            'BB+': 2, 'BB': 1.5, 'BB-': 1,
            'B+': 0.5, 'B': 0, 'B-': -0.5,
            'CCC+': -1, 'CCC': -1.5, 'CCC-': -2,
            'CC': -2.5, 'C': -3, 'D': -4
        }
        
        def parse_rating(rating_str: str) -> float:
            """Extract numeric rating from rating string"""
            if pd.isna(rating_str):
                return np.nan
            # Extract the main rating (e.g., "AA-" from "AA- perspective Stable")
            rating_clean = str(rating_str).split()[0] if rating_str else ''
            return rating_tiers.get(rating_clean, np.nan)
        
        if 'rating_long_term' in result.columns:
            result['long_term_rating_score'] = result['rating_long_term'].apply(parse_rating)
        
        if 'rating_short_term' in result.columns:
            result['short_term_rating_score'] = result['rating_short_term'].apply(parse_rating)
        
        return result
    
    def calculate_passive_income_score(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate passive income score (0-100) based on IMPLEMENTATION_PLAN.md criteria.
        
        Scoring:
        - Yield Score (40 pts): Dividend yield assessment
        - Sustainability (30 pts): Payout ratio, dividend history
        - Stability (20 pts): Market cap, sector leadership
        - Growth (10 pts): Dividend growth potential
        
        Args:
            df: DataFrame with dividend, price, and financial data
            
        Returns:
            DataFrame with passive_income_score column
        """
        result = df.copy()
        
        # Initialize score columns
        result['yield_score'] = 0.0
        result['sustainability_score'] = 0.0
        result['stability_score'] = 0.0
        result['growth_score'] = 0.0
        result['passive_income_score'] = 0.0
        
        # Calculate dividend yield if available
        if 'dividend' in result.columns and 'close' in result.columns:
            result['dividend_yield'] = np.where(
                result['close'] > 0,
                result['dividend'] / result['close'],
                0
            )
            
            # Yield Score (0-40 points)
            # > 8% = 20 pts, 5-8% = 15 pts, < 5% = 5 pts
            result['yield_score'] = np.where(
                result['dividend_yield'] > 0.08, 20,
                np.where(result['dividend_yield'] >= 0.05, 15,
                        np.where(result['dividend_yield'] > 0, 5, 0))
            )
        
        # Sustainability Score (0-30 points)
        # Based on ROE (15 pts) and financial health
        if 'roe' in result.columns:
            result['sustainability_score'] = np.where(
                result['roe'] >= self.thresholds['min_roe'], 15,
                np.where(result['roe'] > 0, 5, 0)
            )
        
        # Add payout ratio assessment if we have net_income and dividends
        if 'net_income' in result.columns and 'dividend' in result.columns:
            # Estimate payout ratio (simplified)
            estimated_payout = np.where(
                result['net_income'] > 0,
                (result['dividend'] * result.get('close', 1)) / result['net_income'],
                np.nan
            )
            # Add up to 15 pts for low payout ratio
            result['sustainability_score'] += np.where(
                estimated_payout <= self.thresholds['max_payout_ratio'], 15,
                np.where(estimated_payout <= 0.9, 10,
                        np.where(estimated_payout <= 1.0, 5, 0))
            )
        
        # Stability Score (0-20 points)
        # Based on debt-to-equity and ratings
        if 'debt_to_equity' in result.columns:
            result['stability_score'] = np.where(
                result['debt_to_equity'] < 1.0, 10,
                np.where(result['debt_to_equity'] < 2.0, 5, 0)
            )
        
        if 'long_term_rating_score' in result.columns:
            result['stability_score'] += np.where(
                result['long_term_rating_score'] >= 5, 10,  # AA- or better
                np.where(result['long_term_rating_score'] >= 3, 5, 0)  # BBB- or better
            )
        
        # Growth Score (0-10 points)
        # Based on net margin (profitability for growth)
        if 'net_margin' in result.columns:
            result['growth_score'] = np.where(
                result['net_margin'] >= 0.10, 10,
                np.where(result['net_margin'] >= 0.05, 7,
                        np.where(result['net_margin'] > 0, 3, 0))
            )
        
        # Calculate total passive income score
        result['passive_income_score'] = (
            result['yield_score'] + 
            result['sustainability_score'] + 
            result['stability_score'] + 
            result['growth_score']
        )
        
        return result
    
    def get_investment_recommendation(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Get investment recommendation based on passive income criteria.
        
        Args:
            df: DataFrame with calculated scores
            
        Returns:
            DataFrame with recommendation column
        """
        result = df.copy()
        
        # Ensure passive_income_score is calculated
        if 'passive_income_score' not in result.columns:
            result = self.calculate_passive_income_score(result)
        
        # Recommendation based on score
        result['investment_recommendation'] = np.where(
            result['passive_income_score'] >= 70, 'STRONG BUY',
            np.where(result['passive_income_score'] >= 50, 'BUY',
                    np.where(result['passive_income_score'] >= 30, 'HOLD', 'AVOID'))
        )
        
        return result


def get_financial_summary(financials_df: pd.DataFrame, symbol: str) -> Dict:
    """
    Get financial summary for a specific symbol.
    
    Args:
        financials_df: DataFrame with financial data
        symbol: Stock symbol to analyze
        
    Returns:
        Dictionary with financial metrics
    """
    if financials_df.empty:
        return {}
    
    symbol_data = financials_df[financials_df['symbol'] == symbol].sort_values('fiscal_year', ascending=False)
    
    if symbol_data.empty:
        return {}
    
    latest = symbol_data.iloc[0]
    previous = symbol_data.iloc[1] if len(symbol_data) > 1 else None
    
    summary = {
        'fiscal_year': int(latest['fiscal_year']) if pd.notna(latest.get('fiscal_year')) else None,
        'revenue': latest.get('revenue'),
        'net_income': latest.get('net_income'),
        'total_debt': latest.get('total_debt'),
        'total_equity': latest.get('total_equity'),
        'cash': latest.get('cash_and_cash_equivalents'),
    }
    
    # Calculate YoY changes if previous year data exists
    if previous is not None:
        if pd.notna(latest.get('revenue')) and pd.notna(previous.get('revenue')) and previous.get('revenue', 0) > 0:
            summary['revenue_growth'] = (latest['revenue'] - previous['revenue']) / previous['revenue']
        
        if pd.notna(latest.get('net_income')) and pd.notna(previous.get('net_income')) and previous.get('net_income', 0) > 0:
            summary['net_income_growth'] = (latest['net_income'] - previous['net_income']) / previous['net_income']
    
    return summary


def get_rating_summary(ratings_df: pd.DataFrame, symbol: str) -> Dict:
    """
    Get rating summary for a specific symbol.
    
    Args:
        ratings_df: DataFrame with ratings data
        symbol: Stock symbol to analyze
        
    Returns:
        Dictionary with rating information
    """
    if ratings_df.empty:
        return {}
    
    symbol_ratings = ratings_df[ratings_df['symbol'] == symbol].sort_values('rating_year', ascending=False)
    
    if symbol_ratings.empty:
        return {}
    
    latest = symbol_ratings.iloc[0]
    
    return {
        'rating_year': int(latest['rating_year']) if pd.notna(latest.get('rating_year')) else None,
        'short_term': latest.get('rating_short_term'),
        'long_term': latest.get('rating_long_term'),
    }