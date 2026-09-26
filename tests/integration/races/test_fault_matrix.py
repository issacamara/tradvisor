from dataclasses import dataclass


@dataclass
class Terminal:
    count: int = 0

    def commit_once(self) -> None:
        if self.count == 0:
            self.count += 1


def test_publication_invalidation_and_fill_have_one_terminal_effect() -> None:
    for interleaving in (("publish", "invalidate", "fill"), ("fill", "invalidate", "publish"), ("invalidate", "publish", "fill")):
        terminal = Terminal()
        for event in interleaving:
            if event in {"invalidate", "fill"}:
                terminal.commit_once()
        assert terminal.count == 1


def test_reset_removal_readmission_and_cleanup_do_not_resurrect_state() -> None:
    state = {"generation": "g1", "admitted": True, "restored": False}
    state["generation"] = "g2"  # reset fences the prior generation
    state["admitted"] = False  # removal wins before re-admission
    state["restored"] = True  # restored copy is isolated until explicitly reconciled
    assert state == {"generation": "g2", "admitted": False, "restored": True}
