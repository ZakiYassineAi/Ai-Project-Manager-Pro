#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
task_manager.py - Core Orchestrator for AI Project Manager System
---------------------------------------------------------------
Author: Jules AI (with deep augmentation)
Purpose:
    - Reads agent-level strategies from agent_prompt.json
    - Loads individual task configs from tasks/*.json
    - Executes tasks in sequence or parallel depending on config
    - Logs all results to /logs and /results
    - Provides foundation for scalable, AI-driven project automation
"""

import os
import json
import glob
import logging
import datetime
import importlib
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========== CONFIG ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "../config/agent_prompt.json")
TASKS_DIR = os.path.join(BASE_DIR, "../tasks")
LOGS_DIR = os.path.join(BASE_DIR, "../logs")
RESULTS_DIR = os.path.join(BASE_DIR, "../results")
PLUGINS_DIR = os.path.join(BASE_DIR, "../plugins")

# Add plugins directory to Python path
import sys
sys.path.append(os.path.join(BASE_DIR, ".."))


os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# ========== LOGGER ==========
log_file = os.path.join(LOGS_DIR, f"task_manager_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TaskManager")


# ========== CORE CLASSES ==========

class AgentBrain:
    """Central AI brain, loads strategies & meta-policies from agent_prompt.json"""
    def __init__(self, config_file=CONFIG_PATH):
        self.policies = {}
        self.load_policies(config_file)

    def load_policies(self, config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                self.policies = json.load(f)
            logger.info(f"Loaded agent policies from {config_file}")
        except Exception as e:
            logger.error(f"Failed to load agent_prompt.json: {e}")
            self.policies = {}

    def decide(self, task):
        """Apply meta-strategy to tasks (can be expanded with AI models)."""
        strategy = self.policies.get("execution_modes", {}).get("standard", "sequential")
        logger.info(f"Decision: executing task {task.get('title')} with {strategy} strategy")
        return strategy


class TaskExecutor:
    """Executes individual tasks from JSON config."""
    def __init__(self, task_file):
        self.task_file = task_file
        self.task = self._load_task()

    def _load_task(self):
        with open(self.task_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def run(self):
        try:
            task_title = self.task.get("title", os.path.basename(self.task_file))
            action = self.task.get("action", "default_action")
            params = self.task.get("instructions", {})

            logger.info(f"Running task: {task_title} | Action: {action}")

            # Dynamically load executor plugin (extensible)
            module_name = f"plugins.{action}_plugin"
            try:
                module = importlib.import_module(module_name)
                result = module.run(params)
                logger.info(f"Plugin {module_name} executed successfully.")
            except ModuleNotFoundError:
                result = f"[WARN] Plugin not found for action: {action}. Task skipped."
                logger.warning(result)
            except Exception as e:
                result = f"[ERROR] Plugin {module_name} failed: {e}"
                logger.error(result + f"\n{traceback.format_exc()}")


            # Save result
            result_file = os.path.join(RESULTS_DIR, f"{self.task.get('id', 'task')}.json")
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump({"task": task_title, "result": result}, f, indent=4, ensure_ascii=False)

            logger.info(f"Task {task_title} completed. Result saved to {result_file}")
            return {"task_id": self.task.get('id'), "status": "success", "result": result}

        except Exception as e:
            error_msg = f"Error executing task {self.task_file}: {e}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return {"task_id": self.task.get('id'), "status": "error", "error": str(e)}


class TaskManager:
    """Main orchestrator to execute tasks with AgentBrain decisions."""
    def __init__(self):
        self.agent = AgentBrain()
        self.tasks = self._load_tasks()

    def _load_tasks(self):
        task_files = glob.glob(os.path.join(TASKS_DIR, "*.json"))
        # Sort tasks by priority from agent_prompt.json if available
        priorities = {t.get('id'): t.get('priority', 'low') for t in [json.load(open(f)) for f in task_files]}
        priority_map = {"high": 2, "medium": 1, "low": 0}

        sorted_files = sorted(task_files, key=lambda f: priority_map.get(priorities.get(json.load(open(f)).get('id'), 'low'), 0), reverse=True)

        logger.info(f"Discovered {len(sorted_files)} task(s) in {TASKS_DIR}")
        return [TaskExecutor(file) for file in sorted_files]

    def run_all(self):
        execution_mode = self.agent.policies.get("execution_modes", {}).get("standard", "sequential")

        if execution_mode == "parallel":
            return self._run_parallel()
        else:
            return self._run_sequential()

    def _run_sequential(self):
        results = []
        logger.info("--- Running tasks sequentially ---")
        for executor in self.tasks:
            result = executor.run()
            results.append(result)
        return results

    def _run_parallel(self):
        results = []
        max_workers = self.agent.policies.get("safety", {}).get("max_parallel_workers", 4)
        logger.info(f"--- Running tasks in parallel (max_workers={max_workers}) ---")
        with ThreadPoolExecutor(max_workers=max_workers) as executor_pool:
            future_map = {executor_pool.submit(exec_task.run): exec_task for exec_task in self.tasks}
            for future in as_completed(future_map):
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f"A parallel task execution failed: {e}\n{traceback.format_exc()}")
                    results.append({"status": "error", "error": str(e)})
        return results


# ========== MAIN ==========
if __name__ == "__main__":
    logger.info("🚀 Starting Task Manager Orchestrator...")
    manager = TaskManager()
    if not manager.tasks:
        logger.warning("No tasks found in the tasks directory. Exiting.")
    else:
        results = manager.run_all()
        logger.info("✅ All tasks completed.")
        final_summary = os.path.join(RESULTS_DIR, f"summary_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(final_summary, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
        logger.info(f"Final summary report saved to {final_summary}")
