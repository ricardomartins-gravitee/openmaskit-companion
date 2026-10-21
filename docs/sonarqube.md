# SonarQube Cloud

The public `openmaskit-companion` repository is connected to the free
SonarQube for OSS plan. SonarQube Cloud's GitHub App analyzes the repository
automatically, including the default branch and active pull requests. New pushes
to those pull requests trigger another analysis. No CI token or scanner workflow
is required.

View the [SonarQube Cloud project](https://sonarcloud.io/project/overview?id=ricardomartins-gravitee_openmaskit-companion).

## Coverage

SonarQube Cloud automatic analysis does not import coverage reports. The
repository's GitHub quality workflow independently measures Python branch
coverage and publishes its report artifact. That report is not sent to Sonar.
SonarQube Cloud's dashboard therefore reports code analysis findings without a
coverage metric. Importing coverage would require switching this project to
CI-based analysis and configuring a scanner; that is not part of the current
setup.

## References

- [SonarQube for OSS plan](https://docs.sonarsource.com/sonarqube-cloud/administering-sonarcloud/managing-subscription/subscription-plans)
- [Automatic analysis with GitHub](https://docs.sonarsource.com/sonarqube-cloud/getting-started/github)
- [Supported languages](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/languages)
- [Coverage overview and CI-based import](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/test-coverage/overview)
