"""
Comprehensive test coverage analysis for BenGER API.
Analyzes test coverage across all critical components and identifies gaps.
"""

import ast
from pathlib import Path
from typing import Dict, List


class TestCoverageAnalyzer:
    """Analyzes test coverage across the API codebase"""

    def __init__(self, api_root_path: str):
        self.api_root = Path(api_root_path)
        self.test_root = self.api_root / "tests"

        # Critical components that must have test coverage
        self.critical_components = {
            "routers": ["auth.py", "users.py", "dashboard.py", "health.py", "projects_api.py"],
            "models": ["project_models.py", "models.py"],
            "auth_module": ["dependencies.py", "models.py", "service.py"],
            "database": ["database.py"],
            "core_services": ["notification_service.py", "user_service.py"],
        }

        # Test categories we should have
        self.test_categories = {
            "unit": [
                "test_auth_router.py",
                "test_users_router.py",
                "test_dashboard_router.py",
                "test_health_router.py",
                "test_projects_router.py",
            ],
            "integration": ["test_complete_workflows.py", "test_api_integration.py"],
            "database": [
                "test_project_annotation_system.py",
                "test_database_schema_alignment.py",
                "test_database_migrations.py",
            ],
        }

    def analyze_source_files(self) -> Dict[str, List[str]]:
        """Analyze source files to identify functions/classes that need testing"""
        source_analysis = {}

        # Analyze routers
        routers_path = self.api_root / "routers"
        if routers_path.exists():
            source_analysis["routers"] = self._analyze_router_files(routers_path)

        # Analyze models
        models_files = [self.api_root / "project_models.py", self.api_root / "models.py"]
        source_analysis["models"] = self._analyze_model_files(models_files)

        # Analyze auth module
        auth_path = self.api_root / "auth_module"
        if auth_path.exists():
            source_analysis["auth_module"] = self._analyze_auth_module(auth_path)

        # Analyze main API file
        main_file = self.api_root / "main.py"
        if main_file.exists():
            source_analysis["main"] = self._analyze_main_file(main_file)

        # Analyze projects API
        projects_file = self.api_root / "projects_api.py"
        if projects_file.exists():
            source_analysis["projects_api"] = self._analyze_projects_api(projects_file)

        return source_analysis

    def _analyze_router_files(self, routers_path: Path) -> List[str]:
        """Analyze router files for endpoints"""
        endpoints = []

        for router_file in routers_path.glob("*.py"):
            if router_file.name == "__init__.py":
                continue

            try:
                with open(router_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # Look for FastAPI route decorators
                        for decorator in node.decorator_list:
                            if isinstance(decorator, ast.Call) and hasattr(decorator.func, 'attr'):
                                if decorator.func.attr in ['get', 'post', 'put', 'delete', 'patch']:
                                    endpoint = f"{router_file.stem}.{node.name}"
                                    endpoints.append(endpoint)
            except Exception as e:
                print(f"Error analyzing {router_file}: {e}")

        return endpoints

    def _analyze_model_files(self, model_files: List[Path]) -> List[str]:
        """Analyze model files for classes and methods"""
        models = []

        for model_file in model_files:
            if not model_file.exists():
                continue

            try:
                with open(model_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        models.append(f"{model_file.stem}.{node.name}")
            except Exception as e:
                print(f"Error analyzing {model_file}: {e}")

        return models

    def _analyze_auth_module(self, auth_path: Path) -> List[str]:
        """Analyze auth module for functions and classes"""
        auth_components = []

        for auth_file in auth_path.glob("*.py"):
            if auth_file.name == "__init__.py":
                continue

            try:
                with open(auth_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                        component = f"auth_module.{auth_file.stem}.{node.name}"
                        auth_components.append(component)
            except Exception as e:
                print(f"Error analyzing {auth_file}: {e}")

        return auth_components

    def _analyze_main_file(self, main_file: Path) -> List[str]:
        """Analyze main.py for app configuration"""
        main_components = []

        try:
            with open(main_file, 'r', encoding='utf-8') as f:
                content = f.read()
                tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if any(
                        decorator.id == 'app'
                        for decorator in node.decorator_list
                        if isinstance(decorator, ast.Attribute) and hasattr(decorator, 'value')
                    ):
                        main_components.append(f"main.{node.name}")
        except Exception as e:
            print(f"Error analyzing main.py: {e}")

        return main_components

    def _analyze_projects_api(self, projects_file: Path) -> List[str]:
        """Analyze projects_api.py for endpoints"""
        project_endpoints = []

        try:
            with open(projects_file, 'r', encoding='utf-8') as f:
                content = f.read()
                tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Look for router decorators
                    for decorator in node.decorator_list:
                        if isinstance(decorator, ast.Call) and hasattr(decorator.func, 'attr'):
                            if decorator.func.attr in ['get', 'post', 'put', 'delete', 'patch']:
                                endpoint = f"projects_api.{node.name}"
                                project_endpoints.append(endpoint)
        except Exception as e:
            print(f"Error analyzing projects_api.py: {e}")

        return project_endpoints

    def analyze_existing_tests(self) -> Dict[str, List[str]]:
        """Analyze existing test files"""
        test_analysis = {"unit": [], "integration": [], "database": [], "other": []}

        if not self.test_root.exists():
            return test_analysis

        # Analyze unit tests
        unit_path = self.test_root / "unit"
        if unit_path.exists():
            test_analysis["unit"] = [f.name for f in unit_path.glob("test_*.py")]

        # Analyze integration tests
        integration_path = self.test_root / "integration"
        if integration_path.exists():
            test_analysis["integration"] = [f.name for f in integration_path.glob("test_*.py")]

        # Find database-related tests
        for test_file in self.test_root.rglob("test_*.py"):
            if any(
                keyword in test_file.name.lower()
                for keyword in ["database", "schema", "migration", "annotation"]
            ):
                test_analysis["database"].append(test_file.name)

        # Find other test files
        for test_file in self.test_root.rglob("test_*.py"):
            if (
                test_file.name not in test_analysis["unit"]
                and test_file.name not in test_analysis["integration"]
                and test_file.name not in test_analysis["database"]
            ):
                test_analysis["other"].append(test_file.name)

        return test_analysis

    def identify_coverage_gaps(
        self, source_analysis: Dict, test_analysis: Dict
    ) -> Dict[str, List[str]]:
        """Identify coverage gaps between source and tests"""
        gaps = {
            "missing_router_tests": [],
            "missing_model_tests": [],
            "missing_auth_tests": [],
            "missing_integration_tests": [],
            "missing_database_tests": [],
        }

        # Check router coverage
        router_endpoints = source_analysis.get("routers", [])
        for endpoint in router_endpoints:
            router_name = endpoint.split('.')[0]
            expected_test = f"test_{router_name}_router.py"
            if expected_test not in test_analysis["unit"]:
                gaps["missing_router_tests"].append(expected_test)

        # Check model coverage
        models = source_analysis.get("models", [])
        model_test_files = [f for f in test_analysis["database"] if "model" in f.lower()]
        if models and not model_test_files:
            gaps["missing_model_tests"].append("test_models_comprehensive.py")

        # Check auth coverage
        auth_components = source_analysis.get("auth_module", [])
        auth_test_files = [f for f in test_analysis["unit"] if "auth" in f.lower()]
        if auth_components and not auth_test_files:
            gaps["missing_auth_tests"].append("test_auth_comprehensive.py")

        # Check integration test coverage
        required_integration_tests = ["test_complete_workflows.py", "test_api_integration.py"]
        for required_test in required_integration_tests:
            if required_test not in test_analysis["integration"]:
                gaps["missing_integration_tests"].append(required_test)

        # Check database test coverage
        required_db_tests = ["test_database_schema_alignment.py", "test_database_migrations.py"]
        for required_test in required_db_tests:
            if required_test not in test_analysis["database"]:
                gaps["missing_database_tests"].append(required_test)

        return gaps

    def generate_coverage_report(self) -> str:
        """Generate comprehensive coverage report"""
        source_analysis = self.analyze_source_files()
        test_analysis = self.analyze_existing_tests()
        gaps = self.identify_coverage_gaps(source_analysis, test_analysis)

        report = []
        report.append("=" * 80)
        report.append("BenGER API Test Coverage Analysis Report")
        report.append("=" * 80)
        report.append("")

        # Source code analysis
        report.append("📊 SOURCE CODE ANALYSIS")
        report.append("-" * 40)
        for category, components in source_analysis.items():
            report.append(f"{category.upper()}: {len(components)} components")
            for component in components[:5]:  # Show first 5
                report.append(f"  • {component}")
            if len(components) > 5:
                report.append(f"  ... and {len(components) - 5} more")
            report.append("")

        # Test coverage analysis
        report.append("🧪 EXISTING TEST COVERAGE")
        report.append("-" * 40)
        for category, tests in test_analysis.items():
            report.append(f"{category.upper()} TESTS: {len(tests)} files")
            for test_file in tests:
                report.append(f"  ✅ {test_file}")
            report.append("")

        # Coverage gaps
        report.append("❌ COVERAGE GAPS IDENTIFIED")
        report.append("-" * 40)
        total_gaps = sum(len(gap_list) for gap_list in gaps.values())
        if total_gaps == 0:
            report.append("🎉 No coverage gaps identified! Excellent test coverage.")
        else:
            for gap_category, missing_tests in gaps.items():
                if missing_tests:
                    report.append(
                        f"{gap_category.upper().replace('_', ' ')}: {len(missing_tests)} missing"
                    )
                    for missing_test in missing_tests:
                        report.append(f"  ❌ {missing_test}")
                    report.append("")

        # Recommendations
        report.append("💡 RECOMMENDATIONS")
        report.append("-" * 40)

        if gaps["missing_router_tests"]:
            report.append("• Create comprehensive router tests for all API endpoints")

        if gaps["missing_model_tests"]:
            report.append("• Add database model tests for relationships and validations")

        if gaps["missing_auth_tests"]:
            report.append("• Implement comprehensive authentication and authorization tests")

        if gaps["missing_integration_tests"]:
            report.append("• Add end-to-end integration tests for complete workflows")

        if gaps["missing_database_tests"]:
            report.append("• Create database migration and schema validation tests")

        if total_gaps == 0:
            report.append("• Test coverage appears comprehensive!")
            report.append("• Consider adding performance and load testing")
            report.append("• Implement test coverage measurement tools")

        report.append("")
        report.append("=" * 80)
        report.append("End of Coverage Analysis Report")
        report.append("=" * 80)

        return "\n".join(report)

    def get_coverage_summary(self) -> Dict:
        """Get numerical coverage summary"""
        source_analysis = self.analyze_source_files()
        test_analysis = self.analyze_existing_tests()
        gaps = self.identify_coverage_gaps(source_analysis, test_analysis)

        total_components = sum(len(components) for components in source_analysis.values())
        total_tests = sum(len(tests) for tests in test_analysis.values())
        total_gaps = sum(len(gap_list) for gap_list in gaps.values())

        coverage_percentage = max(
            0, (total_components - total_gaps) / max(total_components, 1) * 100
        )

        return {
            "total_components": total_components,
            "total_tests": total_tests,
            "total_gaps": total_gaps,
            "coverage_percentage": round(coverage_percentage, 2),
            "status": "EXCELLENT"
            if coverage_percentage >= 90
            else "GOOD"
            if coverage_percentage >= 70
            else "NEEDS_IMPROVEMENT",
        }


def run_coverage_analysis(api_root_path: str = "/Users/sebastiannagl/Code/BenGer/services/api"):
    """Run complete test coverage analysis"""
    analyzer = TestCoverageAnalyzer(api_root_path)

    print("🔍 Running BenGER API Test Coverage Analysis...")
    print()

    # Generate and print report
    report = analyzer.generate_coverage_report()
    print(report)

    # Print summary
    summary = analyzer.get_coverage_summary()
    print()
    print("📈 COVERAGE SUMMARY")
    print("-" * 20)
    print(f"Total Components: {summary['total_components']}")
    print(f"Total Test Files: {summary['total_tests']}")
    print(f"Coverage Gaps: {summary['total_gaps']}")
    print(f"Coverage Estimate: {summary['coverage_percentage']}%")
    print(f"Status: {summary['status']}")

    return analyzer


if __name__ == "__main__":
    analyzer = run_coverage_analysis()
