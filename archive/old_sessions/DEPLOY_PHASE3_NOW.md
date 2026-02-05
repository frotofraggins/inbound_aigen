# Deploy Phase 3 Now - Quick Reference

**Status:** ✅ Ready  
**Time Required:** ~10 minutes  
**Risk:** LOW

---

## One Command Deploy

```bash
./deploy_phase3_complete.sh
```

This does everything:
1. Updates db-migration Lambda
2. Applies WebSocket idempotency migration
3. Applies constraints migration
4. Redeploys trade-stream service

---

## Verify Success

```bash
python3 verify_phase3_fixes.py
```

Expected:
```
✅ PASS - migrations
✅ PASS - constraints
✅ PASS - idempotency
✅ PASS - trade_stream
```

---

## What Gets Fixed

1. **False Success Reporting** → Accurate migration status
2. **Missing Constraints** → Data validation enforced
3. **WebSocket Duplicates** → Idempotency prevents duplicates

---

## If Something Goes Wrong

### Rollback Trade-Stream
```bash
aws ecs update-service \
  --cluster ops-pipeline \
  --service trade-stream \
  --task-definition trade-stream:<previous-revision> \
  --region us-west-2
```

### Check Logs
```bash
aws logs tail /ecs/trade-stream --follow --region us-west-2
```

---

## After Deployment

Monitor for 24 hours:
- Check logs for "Event already processed"
- Verify no duplicate positions
- Confirm constraints working

---

## Files to Read

- `PHASE3_FIXES_SUMMARY.md` - Quick overview
- `PHASE3_PRODUCTION_FIXES.md` - Complete details
- `PHASE3_COMPLETE_STATUS.md` - Full status

---

**Ready?** Run `./deploy_phase3_complete.sh` now! 🚀
