#-------------------------------------------------------------------------
# Project metadata
#-------------------------------------------------------------------------

m4_define( proj_name,         [LLM Project])
m4_define( proj_maintainer,   [Vu-Minh-Thanh Nguyen nvmthanh@hcmus.edu.vn])
m4_define( proj_abbreviation, [llm-p])

#-------------------------------------------------------------------------
# Project version information
#-------------------------------------------------------------------------
# Version information is meant to be managed through a version control
# system's tags and revision numbers. In a working copy the version will
# not be defined here (you should just use the version control system's
# mechanisms). When we make a distribution then we can set the version
# here as formed by the scripts/vcs-version.sh script so that the
# distribution knows what version it came from. If you are not using
# version control then it is fine to set this directly.

m4_define( proj_version, [0.0.0])

#-------------------------------------------------------------------------
# Setup
#-------------------------------------------------------------------------

AC_INIT(proj_name,proj_version,proj_maintainer,proj_abbreviation)
AC_CONFIG_SRCDIR([src/main.py])

#-------------------------------------------------------------------------
# --with-provider
#-------------------------------------------------------------------------

AC_ARG_WITH(provider,
  AS_HELP_STRING([--with-provider],[Provider to infer Large language model]),
  [provider="${with_provider}"],
  [provider=llamacpp])

AC_SUBST([provider])
AC_MSG_NOTICE([using provider: ${provider}])

#-------------------------------------------------------------------------
# --with-model
#-------------------------------------------------------------------------

AC_ARG_WITH(model,
  AS_HELP_STRING([--with-model],[Large language model to use]),
  [model="${with_model}"],
  [model="manual_Mistral_7B"])

AC_SUBST([model])
AC_MSG_NOTICE([using model: ${model}])

#-------------------------------------------------------------------------
# --with-max-token
#-------------------------------------------------------------------------

AC_ARG_WITH(max_token,
  AS_HELP_STRING([--with-max_token],[Max output tokens]),
  [max_token="${with_max_token}"],
  [max_token="2048"])

AC_SUBST([max_token])
AC_MSG_NOTICE([using max token: ${max_token}])

AC_ARG_WITH(temperature,
  AS_HELP_STRING([--with-temperature],[Temperature]),
  [temperature="${with_temperature}"],
  [temperature="0.85"])

AC_SUBST([temperature])
AC_MSG_NOTICE([using temperature: ${temperature}])

#-------------------------------------------------------------------------
# --with-samples
#-------------------------------------------------------------------------

AC_ARG_WITH(samples,
  AS_HELP_STRING([--with-samples],[Number of samples for each problem]),
  [samples="${with_samples}"],
  [samples="1"])

AC_SUBST([samples])
AC_MSG_NOTICE([using samples: ${samples}])

#-------------------------------------------------------------------------
# --with-examples
#-------------------------------------------------------------------------

AC_ARG_WITH(examples,
  AS_HELP_STRING([--with-examples],[Number of examples for ICL context]),
  [examples="${with_examples}"],
  [examples="0"])

AC_SUBST([examples])
AC_MSG_NOTICE([using examples: ${examples}])

#-------------------------------------------------------------------------
# --with-model-manual 
#-------------------------------------------------------------------------

AC_ARG_WITH(model-manual,
  AS_HELP_STRING([--with-model-manual],[Base URL of model]),
  [model_manual="${with_model_manual}"],
  [model_manual=True])

AC_SUBST([model_manual])
AC_MSG_NOTICE([using model-manual: ${model_manual}])

#-------------------------------------------------------------------------
# --with-model-submanual 
#-------------------------------------------------------------------------

AC_ARG_WITH(model-submanual,
  AS_HELP_STRING([--with-model-submanual],[Submanual of model]),
  [model_submanual="${with_model_submanual}"],
  [model_submanual=True])

AC_SUBST([model_submanual])
AC_MSG_NOTICE([using model-submanual: ${model_submanual}])

#-------------------------------------------------------------------------
# --with-task
#-------------------------------------------------------------------------

AC_ARG_WITH(task,
  AS_HELP_STRING([--with-task],[Task to execute: spec-to-rtl or code-complete-iccad2023]),
  [task="${with_task}"],
  [task="code-complete-iccad2023"])

AC_SUBST([task])
AC_MSG_NOTICE([using task: ${task}])

#-------------------------------------------------------------------------
# --with-max-sc-trials
#-------------------------------------------------------------------------

AC_ARG_WITH(max-sc-trials,
  AS_HELP_STRING([--with-max-sc-trials],[Max syntax correction cycles (default: 10)]),
  [max_sc_trials="${with_max_sc_trials}"],
  [max_sc_trials="10"])

AC_SUBST([max_sc_trials])
AC_MSG_NOTICE([using max-sc-trials: ${max_sc_trials}])

#-------------------------------------------------------------------------
# --with-max-tb-trials
#-------------------------------------------------------------------------

AC_ARG_WITH(max-tb-trials,
  AS_HELP_STRING([--with-max-tb-trials],[Max testbench correction cycles (default: 5)]),
  [max_tb_trials="${with_max_tb_trials}"],
  [max_tb_trials="5"])

AC_SUBST([max_tb_trials])
AC_MSG_NOTICE([using max-tb-trials: ${max_tb_trials}])

#-------------------------------------------------------------------------
# --with-revision
#-------------------------------------------------------------------------

AC_ARG_WITH(revision,
  AS_HELP_STRING([--with-revision],[Revision pf LLM]),
  [revision="${with_revision}"],
  [revision="None"])

AC_SUBST([revision])
AC_MSG_NOTICE([using revision: ${revision}])

#-------------------------------------------------------------------------
# --with-yosys-path
#-------------------------------------------------------------------------

AC_ARG_WITH(yosys-path,
  AS_HELP_STRING([--with-yosys-path],[Path to yosys binary for synthesis]),
  [yosys_path="${with_yosys_path}"],
  [yosys_path="/home/share/oss-cad-suite/bin/yosys"])

AC_SUBST([yosys_path])
AC_MSG_NOTICE([using yosys path: ${yosys_path}])

#-------------------------------------------------------------------------
# --with-temp-dir
#-------------------------------------------------------------------------

AC_ARG_WITH(temp-dir,
  AS_HELP_STRING([--with-temp-dir],[Temp directory prefix for Yosys synthesis jobs]),
  [temp_dir="${with_temp_dir}"],
  [temp_dir="/tmp"])

AC_SUBST([temp_dir])
AC_MSG_NOTICE([using temp dir: ${temp_dir}])

#-------------------------------------------------------------------------
# --with-train-dataset-dir
#-------------------------------------------------------------------------

AC_ARG_WITH(train-dataset-dir,
  AS_HELP_STRING([--with-train-dataset-dir],[Output directory for training dataset index files]),
  [train_dataset_dir="${with_train_dataset_dir}"],
  [train_dataset_dir="TrainDataset"])

AC_SUBST([train_dataset_dir])
AC_MSG_NOTICE([using train dataset dir: ${train_dataset_dir}])

#-------------------------------------------------------------------------
# --with-cell-range-start / --with-cell-range-stop
#-------------------------------------------------------------------------

AC_ARG_WITH(cell-range-start,
  AS_HELP_STRING([--with-cell-range-start],[Min logic cell count to extract (inclusive)]),
  [cell_range_start="${with_cell_range_start}"],
  [cell_range_start="0"])

AC_SUBST([cell_range_start])
AC_MSG_NOTICE([using cell range start: ${cell_range_start}])

AC_ARG_WITH(cell-range-stop,
  AS_HELP_STRING([--with-cell-range-stop],[Max logic cell count to extract (inclusive)]),
  [cell_range_stop="${with_cell_range_stop}"],
  [cell_range_stop="5"])

AC_SUBST([cell_range_stop])
AC_MSG_NOTICE([using cell range stop: ${cell_range_stop}])

#-------------------------------------------------------------------------
# --with-flow-steps
#-------------------------------------------------------------------------

AC_ARG_WITH(flow-steps,
  AS_HELP_STRING([--with-flow-steps],[Comma-separated list of flow steps to run (synthesis,extract,filter)]),
  [flow_steps="${with_flow_steps}"],
  [flow_steps="synthesis,extract,filter"])

AC_SUBST([flow_steps])
AC_MSG_NOTICE([using flow steps: ${flow_steps}])

#-------------------------------------------------------------------------
# Output
#-------------------------------------------------------------------------

AC_CONFIG_FILES([Makefile])
AC_OUTPUT