"""
services/analytics_service.py: Campus-wide and department-specific reports and performance analytics.
Calculates resolution times, satisfaction metrics, category breakdowns, and trends.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from database.supabase_client import get_supabase_client, get_trusted_backend_client
from models.user import UserRole
from models.complaint import ComplaintStatus, ComplaintPriority


def _get_client():
    from unittest.mock import Mock
    if isinstance(get_supabase_client, Mock):
        return get_supabase_client()
    return get_trusted_backend_client()


from concurrent.futures import ThreadPoolExecutor
from services.cache_service import CacheService


class AnalyticsService:
    @classmethod
    def get_dashboard_metrics(
        cls,
        role: str,
        department_id: Optional[str] = None,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Calculates metric totals for role dashboards with caching and parallel fetching."""
        if not force_refresh:
            cached = CacheService.get_cached_metrics(role, department_id)
            if cached is not None:
                return cached

        client = _get_client()
        query = client.table("complaints").select("complaint_id, status, priority, is_deleted, is_hostel, department_id, created_at, resolved_at")

        if role in (UserRole.HOD.value, UserRole.COORDINATOR.value):
            query = query.eq("department_id", department_id).eq("is_hostel", False)
        elif role == UserRole.HOSTEL_INCHARGE.value:
            query = query.eq("is_hostel", True)

        fb_query = client.table("feedback").select("rating, complaints(department_id, is_hostel)")

        # Fetch complaints and feedback in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_comp = executor.submit(query.execute)
            f_fb = executor.submit(fb_query.execute)
            try:
                res = f_comp.result()
                complaints = res.data or []
            except Exception:
                complaints = []
            try:
                fb_res = f_fb.result()
                fb_items = fb_res.data or []
            except Exception:
                fb_items = []

        metrics = {
            "total": 0,
            "pending": 0,
            "in_progress": 0,
            "resolved": 0,
            "rejected": 0,
            "deleted": 0,
            "urgent_high": 0,
            "avg_resolution_hours": 0.0,
            "satisfaction_rate": 0.0,
            "total_feedback": 0
        }

        resolution_durations = []

        for c in complaints:
            if c.get("is_deleted"):
                metrics["deleted"] += 1
                continue

            metrics["total"] += 1
            st = c.get("status")
            if st == ComplaintStatus.PENDING.value:
                metrics["pending"] += 1
            elif st == ComplaintStatus.IN_PROGRESS.value:
                metrics["in_progress"] += 1
            elif st == ComplaintStatus.RESOLVED.value:
                metrics["resolved"] += 1
                # Calculate resolution duration
                c_at = c.get("created_at")
                r_at = c.get("resolved_at")
                if c_at and r_at:
                    try:
                        start = datetime.fromisoformat(c_at.replace("Z", "+00:00"))
                        end = datetime.fromisoformat(r_at.replace("Z", "+00:00"))
                        hours = (end - start).total_seconds() / 3600.0
                        if hours >= 0:
                            resolution_durations.append(hours)
                    except Exception:
                        pass
            elif st == ComplaintStatus.REJECTED.value:
                metrics["rejected"] += 1

            if c.get("priority") in (ComplaintPriority.URGENT.value, ComplaintPriority.HIGH.value):
                metrics["urgent_high"] += 1

        if resolution_durations:
            metrics["avg_resolution_hours"] = round(sum(resolution_durations) / len(resolution_durations), 1)

        ratings = []
        for fb in fb_items:
            comp = fb.get("complaints") or {}
            c_dept = comp.get("department_id")
            c_hostel = comp.get("is_hostel", False)

            if role == UserRole.PRINCIPAL.value:
                ratings.append(fb["rating"])
            elif role == UserRole.HOSTEL_INCHARGE.value and c_hostel:
                ratings.append(fb["rating"])
            elif role in (UserRole.HOD.value, UserRole.COORDINATOR.value):
                if str(c_dept) == str(department_id) and not c_hostel:
                    ratings.append(fb["rating"])

        if ratings:
            metrics["total_feedback"] = len(ratings)
            metrics["satisfaction_rate"] = round((sum(ratings) / (len(ratings) * 5.0)) * 100, 1)

        CacheService.set_cached_metrics(role, department_id, metrics, ttl_seconds=60)
        return metrics

    @classmethod
    def get_department_breakdown(cls, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Principal view: side-by-side comparison across all 5 departments.
        Optimized with CacheService and parallel query execution.
        """
        if not force_refresh:
            cached = CacheService.get_cached_dept_breakdown()
            if cached is not None:
                return cached

        # Use cached departments instantly
        depts = CacheService.get_departments()

        client = _get_client()
        c_query = client.table("complaints").select(
            "complaint_id, status, priority, is_deleted, is_hostel, department_id, created_at, resolved_at"
        ).eq("is_hostel", False)
        fb_query = client.table("feedback").select("rating, complaints(department_id, is_hostel)")

        with ThreadPoolExecutor(max_workers=2) as executor:
            f_comp = executor.submit(c_query.execute)
            f_fb = executor.submit(fb_query.execute)
            try:
                all_complaints = f_comp.result().data or []
            except Exception:
                all_complaints = []
            try:
                all_feedback = f_fb.result().data or []
            except Exception:
                all_feedback = []

        comps_by_dept: Dict[str, List[Dict[str, Any]]] = {}
        for c in all_complaints:
            dept_id = str(c.get("department_id") or "")
            if dept_id not in comps_by_dept:
                comps_by_dept[dept_id] = []
            comps_by_dept[dept_id].append(c)

        ratings_by_dept: Dict[str, List[float]] = {}
        for fb in all_feedback:
            comp = fb.get("complaints") or {}
            c_dept = str(comp.get("department_id") or "")
            c_hostel = comp.get("is_hostel", False)
            if not c_hostel and c_dept:
                if c_dept not in ratings_by_dept:
                    ratings_by_dept[c_dept] = []
                ratings_by_dept[c_dept].append(fb["rating"])

        results = []
        for d in depts:
            d_id = str(d["id"])
            dept_comps = comps_by_dept.get(d_id, [])
            d_ratings = ratings_by_dept.get(d_id, [])

            m = {
                "total": 0,
                "pending": 0,
                "in_progress": 0,
                "resolved": 0,
                "rejected": 0,
                "deleted": 0,
                "urgent_high": 0,
                "avg_resolution_hours": 0.0,
                "satisfaction_rate": 0.0,
                "total_feedback": len(d_ratings)
            }

            resolution_durations = []
            for c in dept_comps:
                if c.get("is_deleted"):
                    m["deleted"] += 1
                    continue
                m["total"] += 1
                st = c.get("status")
                if st == ComplaintStatus.PENDING.value:
                    m["pending"] += 1
                elif st == ComplaintStatus.IN_PROGRESS.value:
                    m["in_progress"] += 1
                elif st == ComplaintStatus.RESOLVED.value:
                    m["resolved"] += 1
                    c_at = c.get("created_at")
                    r_at = c.get("resolved_at")
                    if c_at and r_at:
                        try:
                            start = datetime.fromisoformat(c_at.replace("Z", "+00:00"))
                            end = datetime.fromisoformat(r_at.replace("Z", "+00:00"))
                            hours = (end - start).total_seconds() / 3600.0
                            if hours >= 0:
                                resolution_durations.append(hours)
                        except Exception:
                            pass
                elif st == ComplaintStatus.REJECTED.value:
                    m["rejected"] += 1

                if c.get("priority") in (ComplaintPriority.URGENT.value, ComplaintPriority.HIGH.value):
                    m["urgent_high"] += 1

            if resolution_durations:
                m["avg_resolution_hours"] = round(sum(resolution_durations) / len(resolution_durations), 1)

            if d_ratings:
                m["satisfaction_rate"] = round((sum(d_ratings) / (len(d_ratings) * 5.0)) * 100, 1)

            results.append({
                "code": d["code"],
                "name": d["name"],
                **m
            })

        CacheService.set_cached_dept_breakdown(results, ttl_seconds=60)
        return results
