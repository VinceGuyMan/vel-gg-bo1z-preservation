#include maps\_utility;
#include common_scripts\utility;
#include maps\_zombiemode_utility;

main( default_on )
{
	if ( GetDvar( #"zinfo" ) == "" )
	{
		SetDvar( "zinfo", default_on );
	}

	while ( !IsDefined( get_players() ) || get_players().size == 0 )
	{
		wait( 0.1 );
	}

	last_alive = -1;
	last_left = -1;
	last_round = -1;
	last_on = -1;
	last_send = 0;

	for ( ;; )
	{
		on = GetDvarInt( #"zinfo" ) != 0;
		alive = get_enemy_count();
		left = alive;
		if ( IsDefined( level.zombie_total ) && level.zombie_total > 0 )
		{
			left += level.zombie_total;
		}

		cur_round = 1;
		if ( IsDefined( level.round_number ) )
		{
			cur_round = level.round_number;
		}

		if ( on != last_on || ( on && ( alive != last_alive || left != last_left || cur_round != last_round || GetTime() - last_send >= 1000 ) ) )
		{
			players = get_players();
			for ( i = 0; i < players.size; i++ )
			{
				players[i] SetClientDvars( "kisak_mod_tabinfo", on, "zinfo_alive", alive, "zinfo_left", left );
			}
			if ( on )
			{
				LogPrint( "zinfo: alive " + alive + " left " + left + " round " + cur_round + " t " + GetTime() + "\n" );
				PrintLn( "zinfo: alive " + alive + " left " + left + " round " + cur_round + " t " + GetTime() + "\n" );
			}
			last_on = on;
			last_alive = alive;
			last_left = left;
			last_round = cur_round;
			last_send = GetTime();
		}
		wait( 0.2 );
	}
}
