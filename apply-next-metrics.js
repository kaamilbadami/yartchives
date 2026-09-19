(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.YartchivesApplyNextMetrics = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {

  /**
   * Defines and measures recommendation-to-application conversion using the current local action model.
   *
   * Current Architecture Limitations for Durable Aggregate Measurement:
   * - No backend telemetry or user accounts exist.
   * - All interaction state (saved, applied, hidden) is strictly browser-local.
   * - We do not explicitly track impressions ("viewed" events) over time.
   * - We cannot durably aggregate conversion rates across users without introducing new infrastructure.
   *
   * Smallest Future Instrumentation Requirement:
   * - An anonymous, privacy-preserving ping when a recommendation is shown (impression) and when
   *   "Mark applied" is clicked, tied to a transient session ID, to measure true funnel conversion
   *   without user accounts.
   */

  function measureConversion(eligibleRankedPool, localState, topN = 10) {
    if (!eligibleRankedPool || !localState) {
      return { eligible: 0, applied: 0, saved: 0, hidden: 0, viewedNoAction: 0, conversionRate: 0 };
    }

    // The eligible ranked pool should be the ranked jobs BEFORE filtering out applied/hidden,
    // so we can see what the Top 10 would be for this profile, and how the user interacted with them.
    const topEligible = eligibleRankedPool.slice(0, topN);

    const appliedSet = localState.applied || new Set();
    const hiddenSet = localState.hidden || new Set();
    const savedSet = localState.saved || new Set();

    let appliedCount = 0;
    let hiddenCount = 0;
    let savedCount = 0;
    let viewedNoActionCount = 0;

    for (const result of topEligible) {
      // result might be a job object directly or a ranking result { job: { id: ... } }
      const job = result.job || result;
      if (!job || !job.id) continue;

      const isApplied = appliedSet.has(job.id);
      const isHidden = hiddenSet.has(job.id);
      const isSaved = savedSet.has(job.id);

      if (isApplied) appliedCount++;
      if (isHidden) hiddenCount++;
      if (isSaved) savedCount++;

      if (!isApplied && !isHidden && !isSaved) {
        viewedNoActionCount++;
      }
    }

    const eligibleCount = topEligible.length;
    const conversionRate = eligibleCount > 0 ? appliedCount / eligibleCount : 0;

    return {
      eligible: eligibleCount,
      applied: appliedCount,
      saved: savedCount,
      hidden: hiddenCount,
      viewedNoAction: viewedNoActionCount,
      conversionRate
    };
  }



  /**
   * Deterministic analysis layer for recommendation feedback.
   * Produces summaries for Good/Bad rate and bad-suggestion reason distribution
   * without mutating ranking behavior.
   */
  function analyzeFeedback(eligibleRankedPool, feedbackState, topN = 10) {
    if (!eligibleRankedPool || !feedbackState) {
      return { totalRated: 0, goodCount: 0, badCount: 0, goodRate: 0, reasons: {} };
    }

    const topEligible = eligibleRankedPool.slice(0, topN);

    let goodCount = 0;
    let badCount = 0;
    const reasons = {};

    for (const result of topEligible) {
      const job = result.job || result;
      if (!job || !job.id) continue;

      const feedback = feedbackState[job.id];
      if (!feedback) continue;

      if (feedback.type === 'good') {
        goodCount++;
      } else if (feedback.type === 'bad') {
        badCount++;
        const reason = feedback.reason || 'unknown';
        reasons[reason] = (reasons[reason] || 0) + 1;
      }
    }

    const totalRated = goodCount + badCount;
    const goodRate = totalRated > 0 ? goodCount / totalRated : 0;

    return {
      totalRated,
      goodCount,
      badCount,
      goodRate,
      reasons
    };
  }

  return { measureConversion, analyzeFeedback };
});
