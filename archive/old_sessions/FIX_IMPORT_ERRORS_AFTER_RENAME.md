# CRITICAL: Import Errors After Directory Rename

## 🚨 THE PROBLEM

**Error:** `No module named 'alpaca.options'`

**Why:** Kiro renamed directory but some imports still use old path!

```
Old: services/dispatcher/alpaca/
New: services/dispatcher/alpaca_broker/

But code still tries: from alpaca.options import ...
Should be: from alpaca_broker.options import ...
```

---

## 🔍 Files to Check

### **1. broker.py**
```python
# Top of file should have:
from alpaca_broker.options import (  # Not 'alpaca.options'
    AlpacaOptionsAPI,
    get_option_chain_for_strategy,
    calculate_position_size,
    format_option_symbol
)
```

### **2. main.py**
```python
# Should have:
from alpaca_broker.broker import AlpacaPaperBroker  # Not 'alpaca.broker'
```

### **3. Any other files importing from alpaca/**
```bash
# Find all broken imports:
grep -r "from alpaca\." services/dispatcher/ | grep -v alpaca_broker
```

---

## ✅ QUICK FIX

### **Option 1: Fix All Imports (Proper)**

```bash
cd services/dispatcher

# Find and replace all imports
sed -i 's/from alpaca\./from alpaca_broker./g' *.py
sed -i 's/from alpaca\./from alpaca_broker./g' alpaca_broker/*.py

# Rebuild
docker build -t dispatcher .
# Push and deploy
```

### **Option 2: Revert Directory Name (Simpler)**

```bash
cd services/dispatcher

# Rename back
mv alpaca_broker alpaca

# All imports work again
docker build -t dispatcher .
# Push and deploy
```

---

## 🎯 MY RECOMMENDATION

**REVERT the directory rename!**

**Why:**
- Original name `alpaca/` was fine
- Renaming broke imports
- More work to fix all imports
- Easier to just revert

**Command:**
```bash
cd services/dispatcher
mv alpaca_broker alpaca  # Rename back
docker build --no-cache -t dispatcher .
# Push to ECR and deploy
```

**Imports will work immediately!**

---

## 📋 What Happened Timeline

**Yesterday:** System trading correctly (directory: `alpaca/`)  
**Today:** Kiro renamed to `alpaca_broker/`  
**Side Effect:** Some imports still use `from alpaca.` → broke  
**Result:** All trades fall back to simulation

**Fix:** Rename back to `alpaca/` OR update all imports

---

## 🏆 Summary for Kiro

**Problem:** Directory rename broke imports  
**Error:** "No module named 'alpaca.options'"  
**Solution:** 
- **Quick:** Rename back to `alpaca/` (1 minute)
- **Proper:** Fix all imports (10 minutes)

**Recommendation:** Rename back, trades will work immediately!

**Market closes in 1.5 hours** - quick fix is best! ⏰
</result>
</attempt_completion>
