# Reliability Threshold Justification for ELO-Based Ranking System  
**Author**: Onlaj


---

## 1. Introduction  
This document outlines the rationale for selecting **85%** and **94%** as critical reliability thresholds in the ELO-based media ranking system. These thresholds are derived from empirical testing and reflect fundamental properties of pairwise ranking systems under combinatorial constraints. Test results and analyses are included to validate these benchmarks.

---

## 2. Test Results Summary  
The system was tested using synthetic datasets with objective ground-truth rankings. Key observations:  

### Case 1: `n=20` Media Items  
| Metric                     | Value      |
|----------------------------|------------|
| Final Calculated Reliability | 99.1%      |
| Final Real Reliability      | 94.2%      |
| First Crossing Point        | 94.1% at 172.9 votes |

![Reliability Comparison Graph](/docs/reliability_comparison_n20_v2.png)  

### Case 2: `n=50` Media Items  
| Metric                     | Value                       |
|----------------------------|-----------------------------|
| Final Calculated Reliability | 99.1%                       |
| Final Real Reliability      | 94.2%                       |
| Crossing Points             | 92.1–93.0% at 499–522 votes |


![Reliability Comparison Graph](/docs/reliability_comparison_n50_v2.png)  


---

## 3. Threshold Justification  

### 3.1 First Goal: 85% Reliability  
The **85%** threshold represents a **cost-effective inflection point**:  

1. **Rapid Early Gains**:  
   - Resolves ~80% of gross mismatches (e.g., score 20 vs. 1).  
   - Large ELO adjustments dominate early voting.  

2. **Diminishing Returns Begin**:  
   - Remaining errors involve closely ranked pairs (e.g., score 19 vs. 20).  
   - Vote efficiency drops exponentially beyond this point.  

**Empirical Support**:  
- For `n=20`, real reliability reaches 85% at ~100 votes but requires ~170 votes to reach 94%.  
- For `n=50`, 70% of total votes are spent improving from 85% to 94%.  

---

### 3.2 Second Goal: 94% Reliability  
The **94%** threshold reflects the **practical limit** due to:  

1. **Combinatorial Complexity**:  
   - Perfect ordering requires resolving *O(N²)* pairwise relationships.  
   - 6% residual errors persist even at high vote counts.  

2. **ELO Limitations**:  
   - Small ELO differences (e.g., 1169.6 vs. 1168.5) fail to guarantee correct ordering.  
   - Formula overestimates confidence for ambiguous pairs.  

**Empirical Support**:  
- Real reliability plateaus near 94% despite 99% calculated reliability.  
- Crossing points occur near 94%, exposing formula overconfidence.  

---

## 4. Practical Implications  

1. **85% Threshold**:  
   - Recommended for initial deployments or low-stakes rankings.  
   - Balances effort and accuracy effectively.  

2. **94% Threshold**:  
   - Reserved for high-stakes scenarios.  
   - Further improvements yield minimal ROI.  

---

## 5. Conclusion  
The 85% and 94% thresholds reflect a trade-off between voting effort and ranking accuracy. These values are empirically validated and grounded in the combinatorial nature of pairwise ranking systems.  
