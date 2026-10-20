# SonarQube Cloud

The recommended service for this public repository is SonarQube Cloud's free
open-source plan. It supports public repositories and Swift analysis, and avoids
maintaining a local server. The GitHub workflow is committed but remains dormant
until the repository is connected to SonarQube Cloud and its three GitHub
settings are added.

## One-time setup

1. Sign in to [SonarQube Cloud](https://sonarcloud.io/) with the GitHub account
   that owns `ricardomartins-gravitee/openmaskit-companion`.
2. Create/import the GitHub organization or personal account and choose the
   **SonarQube for OSS** plan. Install the SonarQube Cloud GitHub App for this
   repository and import the repository as a bound project. Do not choose a paid
   plan for this setup.
3. In SonarQube Cloud, note the organization key and project key shown for the
   imported project. Do not derive either key from the GitHub repository name.
4. Create a SonarQube Cloud personal access token for analysis and add it to
   GitHub as the repository Actions secret `SONAR_TOKEN`. The token owner's
   account must have Execute Analysis permission for the project.
5. In the GitHub repository's **Settings → Secrets and variables → Actions →
   Variables**, add `SONAR_ORGANIZATION` and `SONAR_PROJECT_KEY` with the exact
   values from SonarQube Cloud. The workflow runs only when both are present.
6. Push to `main`, or run **SonarQube Cloud → Run workflow** from the Actions
   tab. Confirm a successful main-branch analysis before requiring its quality
   gate in branch protection.

The first analysis should use the SonarQube Cloud application setup for GitHub
to establish repository binding. The scanner workflow then supplies analysis
through CI, which is needed to import coverage. SonarQube Cloud calculates no
coverage itself. The workflow generates Python coverage in Cobertura XML and
points the scanner to `coverage.xml`; current Swift analysis is included, but
Swift coverage is not imported by this configuration.

## Pull requests and secrets

The workflow analyzes same-repository pull requests and does not use
`pull_request_target`. Pull requests from forks are skipped because GitHub does
not expose repository secrets to their workflows. Do not work around this by
running fork code in a privileged context or by passing a Sonar token to it.
The normal validation workflow continues to run for fork contributions.

## Scope

`sonar-project.properties` includes the Python package, macOS Swift sources and
their test directories. Generated output, dependency caches and acceptance
fixtures are not added as source roots. Only Python coverage is currently
reported. If Swift coverage is added later, convert its Xcode coverage output to
SonarQube's generic coverage format and import it separately.

## References

- [Getting started with GitHub](https://docs.sonarsource.com/sonarqube-cloud/getting-started/github)
- [Creating a bound GitHub project](https://docs.sonarsource.com/sonarqube-cloud/managing-your-projects/administering-your-projects/devops-platform-integration/github)
- [SonarQube for OSS plan and plan comparison](https://docs.sonarsource.com/sonarqube-cloud/administering-sonarcloud/managing-subscription/subscription-plans)
- [Personal access tokens](https://docs.sonarsource.com/sonarqube-cloud/managing-your-account/managing-tokens)
- [Supported languages](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/languages)
- [Python coverage import](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/test-coverage/python-test-coverage)
- [Coverage overview](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/test-coverage/overview)
