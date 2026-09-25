__all__ = ["EvaluationBundle", "JudgeVerdict", "build_test_set", "evaluate_pipeline"]


def __getattr__(name):
	if name in {"EvaluationBundle", "JudgeVerdict", "evaluate_pipeline"}:
		from .metrics import EvaluationBundle, JudgeVerdict, evaluate_pipeline

		return {
			"EvaluationBundle": EvaluationBundle,
			"JudgeVerdict": JudgeVerdict,
			"evaluate_pipeline": evaluate_pipeline,
		}[name]
	if name == "build_test_set":
		from .testset import build_test_set

		return build_test_set
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
