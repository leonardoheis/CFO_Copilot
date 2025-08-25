# Pull Request Template

## Summary

Brief description of changes

## Checklist

### Code & Implementation
- [ ] Have you run `uv run poe format` and fixed all warnings before submitting 
this PR?
- [ ] Is all the logic in services instead of endpoints?
- [ ] Is the code self-explanatory without requiring comments or documentation?

### Machine Learning Specific
- [ ] Are the data preprocessing steps reproducible? (e.g., deterministic pipelines, seeds set).
- [ ] Model changes are tracked with experiment tracker (e.g., versioned 
artifacts, experiment logs).
- [ ] Can all the notebooks be run top to bottom?
- [ ] Are all the notebooks outputs cleared?

### Documentation
- [ ] Relevant README or docs updated.

---

### Reviewer Guidance
- Ensure clarity: Could the reviewer understand the purpose of the PR without
asking?  
- Ensure reproducibility: Could you re-run the experiment or training with the 
given code and instructions?  
- Ensure maintainability: Does the structure fit into the long-term system
design?  
