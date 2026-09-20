const fs = require('fs');
const assert = require('assert');

let state = {
  saved: new Set(["existing-applied-id", "another-id"]),
  applied: new Set(),
  hidden: new Set(),
  feedback: {}
};

function checkID(jobs) {
   let modified = false;
   const ids = new Set(jobs.map(j => j.id));

   for (let key of ["saved", "applied", "hidden"]) {
       for (let oldId of state[key]) {
          if (!ids.has(oldId)) {
             // what can we do if the id isn't in jobs?
             // We can check if oldId exists in previous_ids of some job
             const matchingJob = jobs.find(j => j.previous_ids && j.previous_ids.includes(oldId));
             if (matchingJob) {
                 state[key].delete(oldId);
                 state[key].add(matchingJob.id);
                 modified = true;
             }
          }
       }
   }

   return modified;
}
