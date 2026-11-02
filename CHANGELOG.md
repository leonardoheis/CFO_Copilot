# CHANGELOG

<!-- version list -->

## v0.5.0 (2026-11-02)

### Bug Fixes

- **data**: Drop mis-scaled SEC share counts
  ([`5462bd5`](https://github.com/leonardoheis/CFO_Copilot/commit/5462bd5d69b9697705361eaa221136fcace0f0e7))

- **playground**: Update log figure names for clarity
  ([`3eb4496`](https://github.com/leonardoheis/CFO_Copilot/commit/3eb449638bead19e16e77ab36ad2f1e6bc4ffd9f))

- **schema**: Rename FRED macro columns for accuracy
  ([`7332722`](https://github.com/leonardoheis/CFO_Copilot/commit/73327224c498f121a6bc3dfe305f6a76e0a4c02c))

### Features

- **data**: Add flags for COVID, structural breaks, and outliers
  ([`86b0dd5`](https://github.com/leonardoheis/CFO_Copilot/commit/86b0dd5b9f52f8c95ab3992d2aeb566dc65a4470))

- **data**: Establish panel store for financial data management
  ([`86b0dd5`](https://github.com/leonardoheis/CFO_Copilot/commit/86b0dd5b9f52f8c95ab3992d2aeb566dc65a4470))

- **data**: Implement load_consolidated function
  ([`4b1692a`](https://github.com/leonardoheis/CFO_Copilot/commit/4b1692a64ce1d1bd0b0182a1db1771e80c8917b3))

- **data**: Implement missing value ledger for financial data
  ([`86b0dd5`](https://github.com/leonardoheis/CFO_Copilot/commit/86b0dd5b9f52f8c95ab3992d2aeb566dc65a4470))

- **data**: Load and validate structural breaks from YAML
  ([`86b0dd5`](https://github.com/leonardoheis/CFO_Copilot/commit/86b0dd5b9f52f8c95ab3992d2aeb566dc65a4470))

- **data**: Re-ingest mis-scaled panels and rebuild panel_long
  ([`185eabf`](https://github.com/leonardoheis/CFO_Copilot/commit/185eabf584e6a0da7559e081d91c39f20552dc44))

- **data**: Update processed data files and reingest ledger
  ([`6b3be3b`](https://github.com/leonardoheis/CFO_Copilot/commit/6b3be3b5d4873d32445805e887ac16d4ebcfc8f9))

- **diagnostics**: Add transform comparison functionality
  ([`2ba8fee`](https://github.com/leonardoheis/CFO_Copilot/commit/2ba8feef9d67ba1d9439c12d68886438a0ed0dc1))

- **docs**: Add code smells remediation implementation plan
  ([`32721ca`](https://github.com/leonardoheis/CFO_Copilot/commit/32721ca799b22fc828b80f841fb2a15bc45c9e2a))

- **docs**: Add plans and specs for shares outstanding fixes
  ([`b122ba1`](https://github.com/leonardoheis/CFO_Copilot/commit/b122ba139e64ca903bb8ea79ac7625efd87c78b7))

- **docs**: Add specifications for EDA and feature engineering
  ([`dd88207`](https://github.com/leonardoheis/CFO_Copilot/commit/dd88207664563c80560185018765def4b0b9b694))

- **docs**: Create specification for NB00 ingestion and consolidation
  ([`dd88207`](https://github.com/leonardoheis/CFO_Copilot/commit/dd88207664563c80560185018765def4b0b9b694))

- **domain**: Add forecast target variables and refactor imports
  ([`6c9c2ad`](https://github.com/leonardoheis/CFO_Copilot/commit/6c9c2adfc5569f446733120d5bde71dd480716b8))

- **eda**: Actionable EDA framework with feature audit and decision table
  ([`fcf1d92`](https://github.com/leonardoheis/CFO_Copilot/commit/fcf1d926123a63355a2a9b0309a6490a9fddaf25))

- **evaluation-harness**: Implement evaluation harness structure
  ([`cac7dce`](https://github.com/leonardoheis/CFO_Copilot/commit/cac7dce31d4110484038584a8a92c8b10c2b3ee8))

- **features**: Add pre-listing flag and training rows logic
  ([`77f0585`](https://github.com/leonardoheis/CFO_Copilot/commit/77f0585f1d4c70089aef318a222cd462e8ae801d))

- **features**: Implement feature service and transformations
  ([`3399949`](https://github.com/leonardoheis/CFO_Copilot/commit/33999498b05c282992f5bbb0922b6cec2a2be113))

- **hon-separation**: Implement HON separation and reverse split
  ([`f37208f`](https://github.com/leonardoheis/CFO_Copilot/commit/f37208fb6ccb42d05db97e10c1004df40e632eb0))

- **playground**: Implement ingestion and consolidation notebook
  ([`dd88207`](https://github.com/leonardoheis/CFO_Copilot/commit/dd88207664563c80560185018765def4b0b9b694))

- **sec_edgar**: Add XBRL processing for quarterly facts
  ([`45b2f3e`](https://github.com/leonardoheis/CFO_Copilot/commit/45b2f3e886095256026c82a89592d1fe9ec256ad))

- **settings**: Add features output path method
  ([`a5a698f`](https://github.com/leonardoheis/CFO_Copilot/commit/a5a698f4043963c07567eb2025dd8b2c8c6a2011))

- **tests**: Add tests for cost of revenue calculations
  ([`be8d588`](https://github.com/leonardoheis/CFO_Copilot/commit/be8d588cd0e40cd4b507b400a2b09cb0b776a288))

- **tests**: Add tests for D&A handling and withheld quarters
  ([`69e5335`](https://github.com/leonardoheis/CFO_Copilot/commit/69e5335698dc34747efaffdd9c0769f7a7e45e2e))

- **tests**: Add tests for SecEdgarSource quarterly frames
  ([`78190c7`](https://github.com/leonardoheis/CFO_Copilot/commit/78190c78e6bd83197059dd972dafcdc4edf7ab9a))

- **tests**: Add tests for sources bundle functionality
  ([`dd88207`](https://github.com/leonardoheis/CFO_Copilot/commit/dd88207664563c80560185018765def4b0b9b694))

- **tracking**: Add experiment tracking capabilities
  ([`86b0dd5`](https://github.com/leonardoheis/CFO_Copilot/commit/86b0dd5b9f52f8c95ab3992d2aeb566dc65a4470))


## v0.4.0 (2025-09-01)

### Features

- **cicd**: Add auto-push in github actions when pre-commit changes files
  ([`a6c2838`](https://github.com/ELC/fastapi-production-template/commit/a6c2838e832b72bfc6a168ac207b4a557fd5e26a))


## v0.3.2 (2025-08-25)

### Bug Fixes

- **cicd**: Update environment configuration in cicd yaml
  ([`545756c`](https://github.com/ELC/fastapi-production-template/commit/545756c4d65bb477786b8b75cb04bab5242ec3ee))


## v0.3.1 (2025-08-25)

### Bug Fixes

- **cicd**: Update environment configuration in cicd yaml
  ([`68a19e3`](https://github.com/ELC/fastapi-production-template/commit/68a19e316b90c01b15617915db838addffe366b6))


## v0.3.0 (2025-08-25)

### Features

- **workflows**: Add production environment configuration
  ([`723e8dc`](https://github.com/ELC/fastapi-production-template/commit/723e8dc597eb0709fa97afa791b1ce982075472f))


## v0.2.1 (2025-08-25)

### Bug Fixes

- **workflows**: Update publish workflow configuration
  ([`49bc0d5`](https://github.com/ELC/fastapi-production-template/commit/49bc0d515cc30f207c618059431ba23240778a6b))


## v0.2.0 (2025-08-25)

### Bug Fixes

- **docs**: Correct numbered list in getting started section
  ([`df3559e`](https://github.com/ELC/fastapi-production-template/commit/df3559e976c3beedd95a7d46594ff565bda36d2f))

- **docs**: Correct typos in documentation
  ([`5384d27`](https://github.com/ELC/fastapi-production-template/commit/5384d27e5eeb337be7fbe4f0062cede80760b8df))

- **exceptions**: Clarify NoTrainedModelError message
  ([`d7a2526`](https://github.com/ELC/fastapi-production-template/commit/d7a2526676e211aaa593bc845447069d71358f26))

- **health**: Improve error message for health check
  ([`21a9673`](https://github.com/ELC/fastapi-production-template/commit/21a96731f092cf4b14ca6c410a0cf0a882cea20c))

- **release**: Implement semantic versioning
  ([`8259e85`](https://github.com/ELC/fastapi-production-template/commit/8259e85b78d99150f6feb365eb47f054f68ca663))

- **workflow**: Correct SonarQube coverage exclusions
  ([`ddcbfdb`](https://github.com/ELC/fastapi-production-template/commit/ddcbfdb08c1b8ce01bd7090d27f98466f46ac875))

- **workflow**: Correct SonarQube coverage exclusions
  ([`3a21313`](https://github.com/ELC/fastapi-production-template/commit/3a21313a6d3ce830f294e7889db435c7f41d480d))

- **workflow**: Update test reporter to jest-junit
  ([`ca01492`](https://github.com/ELC/fastapi-production-template/commit/ca0149236b63c805f99bd35f31cfda490117a44c))

### Features

- Update pre-commit configuration and add uv support
  ([`a317875`](https://github.com/ELC/fastapi-production-template/commit/a317875561c7f3f02df1d4651d790cbe1fbaa048))

- **app**: Scaffold FastAPI application structure
  ([`e1c81d3`](https://github.com/ELC/fastapi-production-template/commit/e1c81d31cbe4f2c82616efaa827d967e3c2c6556))

- **docker**: Add Dockerfile for application setup
  ([`e63c3fe`](https://github.com/ELC/fastapi-production-template/commit/e63c3fef2284510285e3788ca6effd9c16c9a9cb))

- **docs**: Add chapters and visual overview to index
  ([`98f5a9b`](https://github.com/ELC/fastapi-production-template/commit/98f5a9b24c4314afbb58247e87b5e40d3f683285))

- **frontend**: Add streamlit UI
  ([`9fdba40`](https://github.com/ELC/fastapi-production-template/commit/9fdba40c9667387e8a75f23c22dc70ec05871633))

- **frontend**: Restructure pages and add health page
  ([`89ad896`](https://github.com/ELC/fastapi-production-template/commit/89ad896125366b4c28b97171be8056494906ce2a))

- **mappings**: Add py-automapper integration
  ([`48c6c24`](https://github.com/ELC/fastapi-production-template/commit/48c6c24af5e952c7087498a03bd251193bff883e))

- **playground**: Add initial test notebook
  ([`0d89394`](https://github.com/ELC/fastapi-production-template/commit/0d89394d5860f0437ab950fd06b8e1abbb2541e7))

- **prediction**: Enhance prediction and training endpoints
  ([`c471532`](https://github.com/ELC/fastapi-production-template/commit/c471532c06e10195d5166682bfb9104b78bde5c5))

- **tests**: Add health endpoint tests and fixtures
  ([`2845c1b`](https://github.com/ELC/fastapi-production-template/commit/2845c1bac1ada5541564176fb5ae17066b288624))

- **tests**: Add test report generation step
  ([`d6ca254`](https://github.com/ELC/fastapi-production-template/commit/d6ca254c9beedb9e62bbed83fd91aaa184dbc1ba))

- **vscode**: Add launch configuration for debugging
  ([`1e3d50a`](https://github.com/ELC/fastapi-production-template/commit/1e3d50a64f95c91f7014d7139ac8f5ca65893283))
